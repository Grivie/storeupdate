import requests
import json
import firebase_admin
from firebase_admin import credentials, db
import os # Import modul os untuk mengakses variabel lingkungan

# --- KONFIGURASI PENTING ---
SOURCE_URL_JAGEL_STATUS = "https://app.jagel.id/api/get-list?comp_vuid=66984199194ee&paginate=1000&page=1&style=4"
FIREBASE_DB_URL = 'https://grivieproject-default-rtdb.asia-southeast1.firebasedatabase.app/'
DB_PATH = '/toko_data' 

def initialize_firebase():
    """Menginisialisasi koneksi Firebase menggunakan kredensial dari variabel lingkungan."""
    try:
        # Ambil konten kunci layanan dari variabel lingkungan GitHub Secret
        # Ini akan menjadi string JSON
        service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY')
        if not service_account_json:
            print("❌ Variabel lingkungan 'FIREBASE_SERVICE_ACCOUNT_KEY' tidak ditemukan.")
            return False

        # Konversi string JSON menjadi dictionary Python
        service_account_info = json.loads(service_account_json)
        
        cred = credentials.Certificate(service_account_info)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})
        print("✅ Berhasil terhubung ke Firebase.")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ Gagal mengurai JSON dari secret Firebase: {e}")
        return False
    except Exception as e:
        print(f"❌ Gagal terhubung ke Firebase: {e}")
        return False

def fetch_data_from_url(url):
    """Mengambil data JSON dari URL yang diberikan."""
    try:
        print(f"Mengambil data dari {url}...")
        response = requests.get(url, timeout=30)
        response.raise_for_status() 
        data = response.json()
        print(f"✅ Berhasil mengambil data dari {url}.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Gagal mengambil data dari {url}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Gagal mengurai JSON dari {url}: {e}")
        return None

def update_store_status_in_firebase():
    """
    Mengambil status is_open dari Jagel API dan memperbarui Firebase.
    """
    if not initialize_firebase():
        return

    jagel_data = fetch_data_from_url(SOURCE_URL_JAGEL_STATUS)
    if not jagel_data or 'data' not in jagel_data or not isinstance(jagel_data['data'], list):
        print("❌ Gagal: Data dari Jagel API tidak valid atau tidak berisi daftar toko.")
        return

    print("Memperbarui status toko di Firebase...")
    ref = db.reference(DB_PATH)

    updated_count = 0
    skipped_count = 0

    for store_jagel in jagel_data['data']:
        if 'title' in store_jagel and 'view_uid' in store_jagel:
            store_title = store_jagel['title']
            store_uid = store_jagel['view_uid']
            
            firebase_key = f"{store_title} - {store_uid}"
            
            is_open_status = store_jagel.get('is_open')
            close_status_text = store_jagel.get('close_status')

            update_data = {
                'is_open': is_open_status,
                'close_status': close_status_text
            }

            try:
                store_ref = ref.child(firebase_key)
                store_ref.update(update_data)
                print(f"✅ Berhasil memperbarui status untuk '{firebase_key}' (is_open: {is_open_status}).")
                updated_count += 1
            except Exception as e:
                print(f"❌ Gagal memperbarui status untuk '{firebase_key}': {e}")
                skipped_count += 1
        else:
            print(f"⚠️ Melewatkan satu entri dari Jagel API karena tidak memiliki 'title' atau 'view_uid': {store_jagel}")
            skipped_count += 1
    
    message = f"🎉 Proses pembaruan status selesai. Diperbarui: {updated_count}, Dilewati: {skipped_count}."
    print(message)

# Menjalankan fungsi pembaruan status
if __name__ == "__main__":
    update_store_status_in_firebase()
