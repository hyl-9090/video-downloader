#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两个 fMP4(dash) 片段合成一个多轨 fMP4: video.mp4 + audio.m4a -> out.mp4
仅合并轨, 不重编码。片段为 default-base-is-moof, 各 moof/mdat 自包含, 偏移不重算。
输出分块写, 避开 hmdfs 大文件整写截断。
"""
import sys, struct, os

CONTAINERS = {'moov','trak','mdia','minf','stbl','mvex','moof','traf','edts','dinf'}

def u32(b,o): return struct.unpack('>I', b[o:o+4])[0]
def u64(b,o): return struct.unpack('>Q', b[o:o+8])[0]
def p32(v): return struct.pack('>I', v)

def parse_boxes(data, start, end):
    boxes=[]; off=start
    while off+8<=end:
        size=u32(data,off); typ=data[off+4:off+8].decode('latin1'); hdr=8
        if size==1: size=u64(data,off+8); hdr=16
        elif size==0: size=end-off
        if size<8: break
        if typ in CONTAINERS:
            boxes.append({'type':typ,'start':off,'size':size,'hdr':hdr,'children':parse_boxes(data,off+hdr,off+size)})
        else:
            boxes.append({'type':typ,'start':off,'size':size,'hdr':hdr,'children':None})
        off+=size
    return boxes

def to_node(box, data):
    if box['children'] is None:
        return {'type':box['type'],'raw': data[box['start']:box['start']+box['size']]}
    return {'type':box['type'],'children':[to_node(c,data) for c in box['children']]}

def make_box(typ, body):
    return p32(len(body)+8)+typ.encode('latin1')+body

def emit_box(node):
    if 'raw' in node: return node['raw']
    return make_box(node['type'], b''.join(emit_box(c) for c in node['children']))

def find(node, typ):
    if 'raw' in node:
        return node if node['type']==typ else None
    for c in node['children']:
        if c['type']==typ: return c
        r=find(c,typ)
        if r: return r
    return None

def get_child(node, typ):
    if 'raw' in node: return None
    for c in node['children']:
        if c['type']==typ: return c
    return None

def read_track_id(raw):
    # raw 含 size(4)+type(4) 头; tkhd: ver/flags(4) + creation + mod + track_ID
    return u32(raw,28) if raw[0]==1 else u32(raw,20)

def set_track_id(raw, new_id):
    b=bytearray(raw)
    o = 28 if b[0]==1 else 20
    b[o:o+4]=p32(new_id); return bytes(b)

def set_trex_id(raw, new_id):
    b=bytearray(raw); b[12:16]=p32(new_id); return bytes(b)

def set_tfhd_id(raw, new_id):
    b=bytearray(raw); b[12:16]=p32(new_id); return bytes(b)

def main():
    vpath,apath,outpath=sys.argv[1],sys.argv[2],sys.argv[3]
    vdata=open(vpath,'rb').read(); adata=open(apath,'rb').read()

    vtop=parse_boxes(vdata,0,len(vdata)); atop=parse_boxes(adata,0,len(adata))
    vftyp=next((b for b in vtop if b['type']=='ftyp'), None)
    vmoov_box=next((b for b in vtop if b['type']=='moov'), None)
    amoov_box=next((b for b in atop if b['type']=='moov'), None)
    if vmoov_box is None or amoov_box is None:
        print("ERROR: missing moov"); sys.exit(1)

    vmoov=to_node(vmoov_box,vdata); amoov=to_node(amoov_box,adata)

    v_trak=get_child(vmoov,'trak'); a_trak=get_child(amoov,'trak')
    v_tkhd=find(v_trak,'tkhd'); a_tkhd=find(a_trak,'tkhd')
    v_orig=read_track_id(v_tkhd['raw']); a_orig=read_track_id(a_tkhd['raw'])
    print(f"video orig track_id={v_orig}, audio orig track_id={a_orig}")

    NEW_V, NEW_A = 1, 2

    # 编辑 audio trak 的 tkhd
    a_tkhd['raw']=set_track_id(a_tkhd['raw'], NEW_A)
    # audio trex
    a_trex=find(get_child(amoov,'mvex'),'trex')
    a_trex_raw=set_trex_id(a_trex['raw'], NEW_A)
    # video trak tkhd (通常已是1)
    if v_orig!=NEW_V:
        v_tkhd['raw']=set_track_id(v_tkhd['raw'], NEW_V)
    v_trex=find(get_child(vmoov,'mvex'),'trex')
    v_trex_raw=set_trex_id(v_trex['raw'], NEW_V) if v_trex else None

    # 组装 combined moov
    combined_children=[]
    for c in vmoov['children']:
        if c['type']=='mvhd':
            raw=bytearray(c['raw'])
            if raw[0]==1: raw[112:116]=p32(NEW_A+1)
            else: raw[104:108]=p32(NEW_A+1)
            combined_children.append({'type':'mvhd','raw':bytes(raw)})
        elif c['type']=='mvex':
            mv=[]
            for mc in c['children']:
                if mc['type']=='trex' and v_trex_raw is not None:
                    mv.append({'type':'trex','raw':v_trex_raw})
                else:
                    mv.append(mc)
            mv.append({'type':'trex','raw':a_trex_raw})
            combined_children.append({'type':'mvex','children':mv})
        else:
            combined_children.append(c)
    combined_children.append(a_trak)
    combined_moov=make_box('moov', b''.join(emit_box(c) for c in combined_children))

    # 片段配对
    def pair(top):
        frags=[]; pending=None
        for b in top:
            if b['type']=='moof': pending=b
            elif b['type']=='mdat' and pending:
                frags.append((pending,b)); pending=None
        return frags
    vfrags=pair(vtop); afrags=pair(atop)

    # 编辑 moof tfhd
    def edit_moof(moof_box, data, orig, new):
        node=to_node(moof_box,data)
        tfhd=find(node,'tfhd')
        if tfhd and u32(tfhd['raw'],4)==orig:
            tfhd['raw']=set_tfhd_id(tfhd['raw'], new)
        return emit_box(node)

    def chunked(f, data, chunk=1024*1024):
        for i in range(0,len(data),chunk):
            f.write(data[i:i+chunk])

    with open(outpath,'wb') as f:
        chunked(f, emit_box({'type':'ftyp','raw':vftyp and (vdata[vftyp['start']:vftyp['start']+vftyp['size']])}))
        chunked(f, combined_moov)
        for moof,mdat in vfrags:
            chunked(f, edit_moof(moof,vdata,v_orig,NEW_V))
            chunked(f, vdata[mdat['start']:mdat['start']+mdat['size']])
        for moof,mdat in afrags:
            chunked(f, edit_moof(moof,adata,a_orig,NEW_A))
            chunked(f, adata[mdat['start']:mdat['start']+mdat['size']])
    print("WROTE", outpath, os.path.getsize(outpath), "frags v=%d a=%d"%(len(vfrags),len(afrags)))

if __name__=='__main__':
    main()
