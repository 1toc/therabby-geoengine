"""Small deterministic asphalt texture for the road *visual*, not surveyed data."""
import random
import struct
import zlib


def asphalt_png(path, size=128):
    rng=random.Random(9801)
    rows=[]
    for y in range(size):
        row=bytearray()
        for x in range(size):
            grain=rng.randrange(-10,11)
            # Sparse aggregate makes the road legible at eye level without
            # pretending to reproduce any particular real-world pavement.
            fleck=rng.randrange(100)
            grain+=(-24 if fleck<2 else 22 if fleck>97 else 0)
            shade=max(55,min(140,103+grain))
            row.extend((shade,shade+2,shade+2))
        rows.append(b'\0'+row)
    def chunk(tag,data):
        return (struct.pack('>I',len(data))+tag+data+
                struct.pack('>I',zlib.crc32(tag+data)&0xffffffff))
    png=(b'\x89PNG\r\n\x1a\n'+
         chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))+
         chunk(b'IDAT',zlib.compress(b''.join(rows),9))+
         chunk(b'IEND',b''))
    path.write_bytes(png)
    return png
