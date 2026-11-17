#!/usr/bin/env python3
"""只从 secret 恢复本设备的五个 Adreno 固件，不记录内容。"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

NAMES = {'a730_sqe.fw', 'gmu_gen70000.bin', 'a730_zap.mdt', 'a730_zap.b01', 'a730_zap.b02'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    destination = parser.parse_args().destination
    encoded = os.environ['ADRENO_PART_01'] + os.environ['ADRENO_PART_02']
    manifest = json.loads(os.environ['ADRENO_MANIFEST'])
    data = base64.b64decode(encoded, validate=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as archive:
        members = archive.getmembers()
        if {m.name for m in members} != NAMES or len(members) != len(NAMES):
            raise ValueError('固件归档内容不匹配')
        destination.mkdir(parents=True, exist_ok=False)
        for member in members:
            if not member.isfile():
                raise ValueError('固件只能为普通文件')
            content = archive.extractfile(member).read()
            entry = manifest[member.name]
            if len(content) != entry['bytes'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
                raise ValueError('固件分片校验失败')
            (destination / member.name).write_bytes(content)
    print('已恢复并校验五个设备固件文件；内容未输出')


if __name__ == '__main__':
    main()
