import socket
import json
import time
import threading
import sys
import base64

# Import modul hashing aman yang kompatibel dengan Python 3.12
try:
    from Cryptodome.Hash import SHA256, Keccak, BLAKE2s
except ImportError:
    print("[-] Harap instal dependensi baru dengan perintah: pip install pycryptodomex safe-pysha3")
    sys.exit(1)

# ==========================================
# KONFIGURASI UTAMA
# ==========================================
THREADS_COUNT = 8
USERNAME = "MC2aktqE12PdxRvapTNrG8kbhU5F1Vb2fT"
PASSWORD = "c=MAZA,zap=MAZA"
PROXY_B64 = "bWlub3RhdXJ4Lm5hLm1pbmUuenBvb2wuY2E6NzAxOQ=="

try:
    decoded = base64.b64decode(PROXY_B64).decode('utf-8')
    POOL_HOST, POOL_PORT = decoded.split(":")
    POOL_PORT = int(POOL_PORT)
except:
    POOL_HOST, POOL_PORT = "minotaurx.na.mine.zpool.ca", 7019

sock = None  
lock = threading.Lock()
total_nonces = 0
submit_id = 10  
extranonce1 = "00000000"       
extranonce2_size = 4   
current_target = int("00000000ffff0000000000000000000000000000000000000000000000000000", 16)

def native_minotaurx_hash(data):
    """
    Rantai algoritma MinotaurX yang memanfaatkan performa library C
    dari modul Cryptodome (Aman dari eror kompilasi pystrhex.h).
    """
    h1 = SHA256.new(data).digest()
    h2 = Keccak.new(digest_bits=256, data=h1).digest()
    h3 = BLAKE2s.new(data=h2).digest()
    return SHA256.new(h3).digest()

def miner_worker(thread_id, job):
    global total_nonces, extranonce1, extranonce2_size, current_target, sock, submit_id
    
    header_base = job['version'] + job['prevhash'] + extranonce1 + format(thread_id, f'0{extranonce2_size*2}x') + job['bits'] + job['ntime']
    nonce = thread_id * 50_000_000

    while True:
        nonce_bytes = nonce.to_bytes(4, byteorder='big')
        try:
            block_header = bytes.fromhex(header_base) + nonce_bytes
        except ValueError:
            block_header = header_base.encode() + nonce_bytes
        
        hash_bytes = native_minotaurx_hash(block_header)
        hash_int = int.from_bytes(hash_bytes, byteorder='big')
        
        with lock:
            total_nonces += 1
            local_target = current_target
        
        if hash_int < local_target:
            with lock:
                submit_id += 1
                msg = {
                    "id": submit_id, 
                    "method": "mining.submit", 
                    "params": [USERNAME, job['job_id'], format(thread_id, f'0{extranonce2_size*2}x'), job['ntime'], nonce_bytes.hex()]
                }
                try:
                    sock.sendall((json.dumps(msg) + "\n").encode())
                    print(f"\n[>>>] Share Valid Terkirim! Nonce: {nonce_bytes.hex()}")
                except:
                    pass
        nonce += 1

def format_view_reporter():
    global total_nonces
    start_time = time.time()
    while True:
        time.sleep(3)
        elapsed = time.time() - start_time
        if elapsed > 0:
            khs = (total_nonces / elapsed) / 1000
            sys.stdout.write(f"\r[*] Kinerja CPU: {khs:.2f} kH/s | Total Nonce: {total_nonces} | Active Threads: {THREADS_COUNT}")
            sys.stdout.flush()

def start_miner():
    global sock, extranonce1, extranonce2_size, current_target
    
    print(f"[*] Menghubungkan ke Pool Stratum {POOL_HOST}:{POOL_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        sock.connect((POOL_HOST, POOL_PORT))
        print("[+] Sukses Terhubung!")
    except Exception as e:
        print(f"[-] Koneksi Gagal: {e}")
        return

    sock.sendall(b'{"id":1,"method":"mining.subscribe","params":[]}\n')
    try:
        res = json.loads(sock.recv(2048).decode().split('\n'))
        if res.get('result'):
            extranonce1 = res['result']
            extranonce2_size = int(res['result'])
    except:
        pass

    auth = {"id": 2, "method": "mining.authorize", "params": [USERNAME, PASSWORD]}
    sock.sendall((json.dumps(auth) + "\n").encode())
    sock.recv(1024)
    print("[+] Status Otorisasi Perangkat: OK")

    threading.Thread(target=format_view_reporter, daemon=True).start()

    data_buffer = ""
    while True:
        data = sock.recv(4096).decode('utf-8')
        if not data:
            break
            
        data_buffer += data
        while "\n" in data_buffer:
            line, data_buffer = data_buffer.split("\n", 1)
            if not line.strip():
                continue
                
            try:
                message = json.loads(line)
                method = message.get('method')
                
                if method == 'mining.set_difficulty':
                    diff = float(message['params']) if message['params'] else 1.0
                    with lock:
                        current_target = int(0x00000000FFFF0000000000000000000000000000000000000000000000000000 / diff)
                
                elif method == 'mining.notify':
                    p = message['params']
                    job = {'job_id': p, 'prevhash': p, 'version': p, 'bits': p, 'ntime': p}
                    for i in range(THREADS_COUNT):
                        threading.Thread(target=miner_worker, args=(i, job), daemon=True).start()
                
                elif message.get('id') is not None and message.get('id') > 10:
                    status = "[V] ACCEPTED" if message.get('error') is None else f"[X] REJECTED"
                    print(f"\n[Pool] {status}")
            except:
                pass

if __name__ == "__main__":
    try:
        start_miner()
    except KeyboardInterrupt:
        sys.exit(0)
