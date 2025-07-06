import requests
import json
import firebase_admin
from firebase_admin import credentials, db
import os # Import the os module to access environment variables

# --- PENTING: KONFIGURASI ---
# URL untuk mengambil status is_open secara realtime dari Jagel API
SOURCE_URL_JAGEL_STATUS = "https://app.jagel.id/api/get-list?comp_vuid=66984199194ee&paginate=1000&page=1&style=4"

# URL database Firebase Realtime Anda
FIREBASE_DB_URL = 'https://grivieproject-default-rtdb.asia-southeast1.firebasedatabase.app/'
# Path di database Firebase tempat data toko disimpan, dengan view_uid sebagai kunci
DB_PATH = '/toko_data' 

def initialize_firebase():
    """
    Menginisialisasi koneksi Firebase Admin SDK.
    Kredensial diambil dari variabel lingkungan 'FIREBASE_SERVICE_ACCOUNT_KEY',
    yang harus disetel sebagai GitHub Secret jika menggunakan GitHub Actions.
    """
    try:
        # Mengambil konten kunci layanan dari variabel lingkungan (string JSON)
        service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY')
        if not service_account_json:
            print("❌ Variabel lingkungan 'FIREBASE_SERVICE_ACCOUNT_KEY' tidak ditemukan.")
            print("   Pastikan secret ini telah diatur di lingkungan Anda (misalnya GitHub Actions).")
            return False

        # Mengonversi string JSON menjadi dictionary Python
        service_account_info = json.loads(service_account_json)
        
        # Menginisialisasi Firebase Admin SDK dengan kredensial
        cred = credentials.Certificate(service_account_info)
        if not firebase_admin._apps: # Memastikan Firebase tidak diinisialisasi ulang
            firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})
        print("✅ Berhasil terhubung ke Firebase.")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ Gagal mengurai JSON dari secret Firebase: {e}")
        print("   Pastikan nilai secret 'FIREBASE_SERVICE_ACCOUNT_KEY' adalah JSON yang valid.")
        return False
    except Exception as e:
        print(f"❌ Gagal terhubung ke Firebase: {e}")
        return False

def fetch_data_from_url(url):
    """
    Mengambil data JSON dari URL yang diberikan.
    Menyertakan logging detail untuk debugging.
    """
    try:
        print(f"Mengambil data dari {url}...")
        response = requests.get(url, timeout=30)
        response.raise_for_status() # Akan memunculkan HTTPError untuk status kode 4xx/5xx
        
        # --- LOG DEBUGGING ---
        print(f"Respons HTTP Status Code: {response.status_code}")
        print(f"Respons HTTP Content-Type: {response.headers.get('Content-Type')}")
        # Cetak beberapa karakter pertama dari respons teks untuk inspeksi cepat
        print(f"Respons HTTP Raw Text (200 karakter pertama): {response.text[:200]}...")
        # --- AKHIR LOG DEBUGGING ---

        data = response.json()
        print(f"✅ Berhasil mengambil data dari {url}.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Gagal mengambil data dari {url}: {e}")
        print(f"   Pastikan URL benar dan dapat diakses.")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Gagal mengurai JSON dari {url}. Respons mungkin bukan JSON yang valid. Error: {e}")
        print(f"Respons yang gagal diurai (200 karakter pertama): {response.text[:200]}...")
        return None

def update_store_status_in_firebase():
    """
    Fungsi utama untuk mengambil status is_open dan close_status dari Jagel API
    dan memperbarui Firebase Realtime Database.
    """
    if not initialize_firebase():
        return

    jagel_data = fetch_data_from_url(SOURCE_URL_JAGEL_STATUS)
    
    # --- LOG DEBUGGING ---
    print(f"Tipe data jagel_data yang diterima: {type(jagel_data)}")
    if isinstance(jagel_data, dict):
        print(f"Kunci yang ada di jagel_data: {list(jagel_data.keys())}")
        if 'data' in jagel_data:
            print(f"Tipe data jagel_data.get('data'): {type(jagel_data.get('data'))}")
            if isinstance(jagel_data.get('data'), dict) and 'data' in jagel_data.get('data'):
                print(f"Tipe data jagel_data['data'].get('data'): {type(jagel_data['data'].get('data'))}")
    # --- AKHIR LOG DEBUGGING ---

    stores_to_process = None
    if isinstance(jagel_data, list):
        # Case 1: Respons API adalah daftar langsung dari objek toko (misal: [toko1, toko2, ...])
        stores_to_process = jagel_data
        print("✅ Data Jagel API adalah daftar langsung dari toko.")
    elif isinstance(jagel_data, dict) and 'data' in jagel_data and \
         isinstance(jagel_data['data'], dict) and 'data' in jagel_data['data'] and \
         isinstance(jagel_data['data']['data'], list):
        # Case 2: Respons API adalah kamus dengan kunci 'data' yang berisi kamus lain,
        #         dan kamus kedua ini memiliki kunci 'data' yang berisi daftar toko (struktur paginasi)
        stores_to_process = jagel_data['data']['data']
        print("✅ Data Jagel API adalah kamus bersarang dengan daftar toko di 'data.data'.")
    elif isinstance(jagel_data, dict) and 'data' in jagel_data and isinstance(jagel_data['data'], list):
        # Case 3: Respons API adalah kamus dengan kunci 'data' yang berisi daftar (struktur non-paginasi)
        stores_to_process = jagel_data['data']
        print("✅ Data Jagel API adalah kamus dengan kunci 'data' yang berisi daftar toko.")
    elif isinstance(jagel_data, dict) and 'view_uid' in jagel_data and 'title' in jagel_data:
        # Case 4: Respons API adalah objek toko tunggal (misal: {toko1})
        stores_to_process = [jagel_data] # Bungkus dalam daftar agar bisa diiterasi
        print("✅ Data Jagel API adalah objek toko tunggal.")
    else:
        print("❌ Gagal: Data dari Jagel API tidak valid atau tidak berisi format toko yang dikenali.")
        if jagel_data:
            # Cetak sebagian struktur data yang diterima untuk membantu debugging
            print(f"Struktur data yang diterima: {json.dumps(jagel_data, indent=2)[:500]}...") 
        return

    print("Memperbarui status toko di Firebase...")
    ref = db.reference(DB_PATH)

    updated_count = 0
    skipped_count = 0

    for store_jagel in stores_to_process:
        # Memastikan objek toko memiliki 'title' dan 'view_uid' sebelum diproses
        if 'title' in store_jagel and 'view_uid' in store_jagel:
            # Menggunakan view_uid sebagai kunci Firebase untuk toko
            firebase_key = store_jagel['view_uid']
            
            # Mengambil status is_open dan close_status dari data Jagel
            is_open_status = store_jagel.get('is_open')
            close_status_text = store_jagel.get('close_status')

            # Data yang akan diupdate di Firebase
            update_data = {
                'is_open': is_open_status,
                'close_status': close_status_text
            }

            try:
                # Mengakses referensi toko di Firebase menggunakan view_uid sebagai kunci
                store_ref = ref.child(firebase_key)
                # Menggunakan .update() untuk hanya mengubah bidang tertentu tanpa menimpa seluruh objek
                store_ref.update(update_data)
                print(f"✅ Berhasil memperbarui status untuk toko dengan UID '{firebase_key}' (is_open: {is_open_status}).")
                updated_count += 1
            except Exception as e:
                print(f"❌ Gagal memperbarui status untuk toko dengan UID '{firebase_key}': {e}")
                skipped_count += 1
        else:
            print(f"⚠️ Melewatkan satu entri dari Jagel API karena tidak memiliki 'title' atau 'view_uid' yang diperlukan: {store_jagel}")
            skipped_count += 1
    
    message = f"🎉 Proses pembaruan status selesai. Diperbarui: {updated_count}, Dilewati: {skipped_count}."
    print(message)

# Menjalankan fungsi utama ketika skrip dieksekusi
if __name__ == "__main__":
    update_store_status_in_firebase()
