#!/usr/bin/env python3
'''
ever needed a network diagram that was always up to date?

here's a script that imports your rancid archive and connects
the dots using any /30s as circuits and creates a graphviz dot
from the results

just invoke with the name of your rancid router.db; if you
have more than cisco/juniper/cisco_switch you'll need to
write an importer method to pull the ip address. stderr will
be the raw circuit endpoints. stdout will be the dot graph.

this ignores broadcast interfaces with multiple devices
on it in the dot part. the stderr linkage will show it though.
my backbone testcase was large enough without that clutter as is.

there are better ways to visualize for large models like this
but this was cutting edge in 2002 when i wrote it. 2022 was
updating to python3. woop
--
kehlarn
'''

import radix
import re
import pathlib
import math
import struct
import socket
import sys

class rancidmodel(object):
    def mask2len(self,m):
        return 32-int(math.log(0xffffffff-struct.unpack('!L',socket.inet_aton(m))[0]+1,2))
    def prefix(self,h,m):
        if isinstance(m,str):
            return '{}/{}'.format(h,self.mask2len(m))
        elif isinstance(m,int) and m <=128:
            return '{}/{}'.format(h,m)
    def __init__(self,f):
        self.fib=radix.Radix()
        self.top={}
        self.handler={
                'juniper':self.ingest_juniper,
                'cisco':self.ingest_cisco,
                'cisco_switch':self.ingest_ciscoswitch,
                }
        self.loadtop(f)
        self.basedir=pathlib.Path(f).parent
    def loadtop(self,f):
        with open(f,'rt') as dsn:
            for line in dsn:
                comment=line.rfind('#')
                if comment >= 0:
                    line=line[:comment]
                try:
                    node,vendor,status=line.split(':')
                except (ValueError) as e:
                    pass
                else:
                    if status[0:2] == 'up': #dodge fileformat issue
                        self.top.setdefault(vendor,{})[node]=True
                    else:
                        pass
    def ingest(self):
        for vendor in self.top:
            for node in self.top[vendor]:
                if vendor in self.handler:
                    self.handler[vendor](node)
    def ingest_juniper(self,n):
        rx=re.compile(r'^# sh int terse:\s+(\S+)\s+(up|down)\s+(up|down)\s+inet\s+(\S+)')
        with open(self.basedir.joinpath('configs',n),'rt') as cfg:
            for line in cfg:
                k=rx.search(line)
                if k:
                    iface,admin,link,addr=k.groups()
                    node=self.fib.add(addr)
                    if node:
                        node.data[addr]=[n,iface]
                else:
                    pass
    def ingest_cisco(self,n):
        with open(self.basedir.joinpath('configs',n),'rt') as cfg:
            #if n == 'wr1.ams2':
            #    import pdb
            #    pdb.set_trace()
            for line in cfg:
                ifacec=re.search(r'^interface\s+(\S+)$',line)
                if ifacec:
                    iface=ifacec.group(1)
                else:
                    ipaddrc=re.search(r'^\s+ip\s+address\s+(\S+)\s+(\S+)$',line)
                    if ipaddrc:
                        host,mask=ipaddrc.group(1,2)
                        prefix=self.prefix(host,mask)
                        node=self.fib.add(prefix)
                        if node:
                            node.data[prefix]=[n,iface]
                    else:
                        endif=re.search(r'^\s+!',line)
                        if endif:
                            iface=None
    def ingest_ciscoswitch(self,n):
        with open(self.basedir.joinpath('configs',n),'rt') as cfg:
            for line in cfg:
                ifacec=re.search(r'^set interface\s+(\S+)\s+(\d+)\s+(\S+)/(\S+)',line)
                if ifacec:
                    iface,vlan,host,mask=ifacec.groups()
                    prefix=self.prefix(host,mask)
                    node=self.fib.add(prefix)
                    if node:
                        node.data[prefix]=[n,iface]
    def graphvizdot(self):
        print('''
graph gx {
    rankdir=LR;
    dim=3;
    graph [bgcolor=black,ranksep=0.5];
    node [shape=Mrecord,bgcolor=black,
    fontcolor=yellow,color=cyan,
    fontsize=14,fontname="Times-Roman"];
    edge [color=yellow];
''')
        if True: #debug model on stderr
            for p in self.fib:
                if len(p.data.keys())>=2:
                    for addr in sorted(p.data.keys(),
                            key=lambda x:struct.unpack('!L',socket.inet_aton(x.split('/')[0]))):
                        print(addr,*p.data[addr],end='; ',file=sys.stderr)
                    print('',file=sys.stderr)
        #else:
        if True: #dump dot on stdout
            l=[]
            g={}
            xf={}
            for p in self.fib:
                if len(p.data.keys())==2:   #only deal with /30 for backbone purposes
                    for addr in p.data.keys():
                        n,i=p.data[addr]
                        g.setdefault(n,{})[i]=True
                    l.append([k[1] for k in p.data.items()])
            for node in g:
                print('    {}[label="{}'.format(node.replace('.','_').replace('-','_'),node),end='')
                for porti,port in enumerate(sorted(g[node].keys())):
                    xf.setdefault(node,{})[port]=porti
                    print('|<{}>{}'.format('{}_{}'.format(node.replace('.','_').replace('-','_'),porti),port),end='')
                print('"];')
            for (na,pa),(nz,pz) in l:
                print('    {}:{}--{}:{};'.format(
                    na.replace('.','_').replace('-','_'),
                    '{}_{}'.format(na.replace('.','_').replace('-','_'),xf[na][pa]),
                    nz.replace('.','_').replace('-','_'),
                    '{}_{}'.format(nz.replace('.','_').replace('-','_'),xf[nz][pz])))
            print('    }')

if __name__=='__main__':
    try:
        rancid=rancidmodel(sys.argv[1])
        rancid.ingest()
        rancid.graphvizdot()
    except (BrokenPipeError) as e:
        pass
