"""Save Jira credentials encrypted for the current Windows account (DPAPI)."""
import argparse
import base64
import ctypes
import getpass
import json
import os
import sys
from pathlib import Path
from ctypes import wintypes

def protect(token):
    if os.name != 'nt':
        raise RuntimeError('Encrypted storage requires Windows. Use JIRA_EMAIL/JIRA_API_TOKEN on other systems.')
    class Blob(ctypes.Structure):
        _fields_ = [('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    raw = token.encode('utf-8')
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    src, dst = Blob(len(raw),buf), Blob()
    crypt = ctypes.WinDLL('crypt32',use_last_error=True)
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    crypt.CryptProtectData.restype = wintypes.BOOL
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not crypt.CryptProtectData(ctypes.byref(src),'CCON BA Desk Jira',None,None,None,1,ctypes.byref(dst)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return base64.b64encode(ctypes.string_at(dst.pbData,dst.cbData)).decode('ascii')
    finally:
        kernel.LocalFree(dst.pbData)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stdin-json',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    data=json.loads(sys.stdin.readline()) if args.stdin_json else {'email':input('Atlassian email: ').strip(),'token':getpass.getpass('Jira API token (hidden): ').strip()}
    if not data.get('email') or not data.get('token'):
        raise ValueError('Email and token are required.')
    path=Path(__file__).resolve().parent/'.jira-credentials.json'
    encrypted={'email':data['email'],'tokenDpapi':protect(data['token'])}
    path.write_text(json.dumps(encrypted,indent=2),encoding='utf-8')
    print('Jira credentials saved encrypted for this Windows account.')

if __name__=='__main__':
    main()
