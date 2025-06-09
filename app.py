from flask import Flask, render_template, request, redirect, url_for, send_file
from supabase import create_client, Client
from datetime import datetime, date
import pandas as pd
from io import BytesIO
import json
import os
from dotenv import load_dotenv

app = Flask(__name__)

# Muat variabel lingkungan dari .env
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

# Debugging: Cetak variabel lingkungan untuk memeriksa
print(f"SUPABASE_URL: {supabase_url}")
print(f"SUPABASE_KEY: {'*' * len(supabase_key) if supabase_key else None}")

# Validasi variabel lingkungan
if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL dan SUPABASE_KEY harus didefinisikan di file .env")

try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    raise ValueError(f"Gagal menginisialisasi klien Supabase: {str(e)}")

# Kategori default
KATEGORI_PENGELUARAN = ['Makanan', 'Transportasi', 'Hiburan', 'Belanja', 'Lainnya']
KATEGORI_PEMASUKAN = ['Gaji', 'Hadiah', 'Freelance', 'Investasi', 'Lainnya']

@app.route('/')
def index():
    today = date.today()
    bulan = request.args.get('bulan', today.month, type=int)
    tahun = request.args.get('tahun', today.year, type=int)

    # Ambil transaksi
    try:
        response = supabase.table('transaksi').select('*').eq('bulan', bulan).eq('tahun', tahun).order('tanggal', desc=True).execute()
        transaksi = response.data or []
    except Exception as e:
        print(f"Error fetching transaksi: {e}")
        transaksi = []

    total_pemasukan = sum(float(t['jumlah']) for t in transaksi if t['tipe'] == 'pemasukan')
    total_pengeluaran = sum(float(t['jumlah']) for t in transaksi if t['tipe'] == 'pengeluaran')
    saldo = total_pemasukan - total_pengeluaran

    # Data untuk diagram pie
    pengeluaran_kategori = {k: 0.0 for k in KATEGORI_PENGELUARAN}
    for t in transaksi:
        if t['tipe'] == 'pengeluaran' and t['kategori'] in pengeluaran_kategori:
            pengeluaran_kategori[t['kategori']] += float(t['jumlah'])
    chart_data = {
        'labels': list(pengeluaran_kategori.keys()),
        'data': [float(v) for v in pengeluaran_kategori.values()]
    }
    if not any(chart_data['data']):
        chart_data['data'] = [0.0] * len(chart_data['labels'])
    print(f"chart_data: {json.dumps(chart_data)}")  # Debugging

    # Data untuk diagram garis
    tren_data = {'labels': [], 'pemasukan': [], 'pengeluaran': []}
    for i in range(5, -1, -1):
        bulan_tren = (today.month - i - 1) % 12 + 1
        tahun_tren = today.year if bulan_tren <= today.month else today.year - 1
        try:
            tren_response = supabase.table('transaksi').select('jumlah, tipe').eq('bulan', bulan_tren).eq('tahun', tahun_tren).execute()
            tren_transaksi = tren_response.data or []
        except Exception as e:
            print(f"Error fetching tren_transaksi: {e}")
            tren_transaksi = []
        tren_pemasukan = sum(float(t['jumlah']) for t in tren_transaksi if t['tipe'] == 'pemasukan')
        tren_pengeluaran = sum(float(t['jumlah']) for t in tren_transaksi if t['tipe'] == 'pengeluaran')
        tren_data['labels'].append(f"{bulan_tren}/{tahun_tren}")
        tren_data['pemasukan'].append(float(tren_pemasukan))
        tren_data['pengeluaran'].append(float(tren_pengeluaran))
    print(f"tren_data: {json.dumps(tren_data)}")  # Debugging

    # Status anggaran
    try:
        anggaran_response = supabase.table('anggaran').select('*').eq('bulan', bulan).eq('tahun', tahun).execute()
        anggaran = anggaran_response.data or []
    except Exception as e:
        print(f"Error fetching anggaran: {e}")
        anggaran = []
    anggaran_status = []
    for a in anggaran:
        total_kategori = sum(float(t['jumlah']) for t in transaksi if t['kategori'] == a['kategori'] and t['tipe'] == 'pengeluaran')
        status = {
            'kategori': a['kategori'],
            'batas': float(a['batas']),
            'terpakai': total_kategori,
            'sisa': float(a['batas']) - total_kategori,
            'melebihi': total_kategori > float(a['batas'])
        }
        anggaran_status.append(status)

    # Target tabungan
    try:
        tabungan_response = supabase.table('tabungan').select('*').execute()
        tabungan = tabungan_response.data or []
    except Exception as e:
        print(f"Error fetching tabungan: {e}")
        tabungan = []

    return render_template('index.html', transaksi=transaksi, saldo=saldo, chart_data=json.dumps(chart_data),
                           tren_data=json.dumps(tren_data), anggaran_status=anggaran_status,
                           tabungan=tabungan, bulan=bulan, tahun=tahun)

@app.route('/tambah_transaksi', methods=['GET', 'POST'])
def tambah_transaksi():
    if request.method == 'POST':
        try:
            deskripsi = request.form['deskripsi']
            jumlah = float(request.form['jumlah'])
            tipe = request.form['tipe']
            kategori = request.form['kategori']
            tanggal = datetime.strptime(request.form['tanggal'], '%Y-%m-%d').date()
            transaksi_baru = {
                'deskripsi': deskripsi,
                'jumlah': jumlah,
                'tipe': tipe,
                'kategori': kategori,
                'tanggal': tanggal.isoformat(),
                'bulan': tanggal.month,
                'tahun': tanggal.year
            }
            supabase.table('transaksi').insert(transaksi_baru).execute()
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Error inserting transaksi: {e}")
            return render_template('tambah_transaksi.html', error=str(e), kategori_pengeluaran=KATEGORI_PENGELUARAN,
                                   kategori_pemasukan=KATEGORI_PEMASUKAN)
    return render_template('tambah_transaksi.html', kategori_pengeluaran=KATEGORI_PENGELUARAN,
                           kategori_pemasukan=KATEGORI_PEMASUKAN)

@app.route('/hapus_transaksi/<int:id>')
def hapus_transaksi(id):
    try:
        supabase.table('transaksi').delete().eq('id', id).execute()
    except Exception as e:
        print(f"Error deleting transaksi: {e}")
    return redirect(url_for('index'))

@app.route('/tambah_anggaran', methods=['GET', 'POST'])
def tambah_anggaran():
    if request.method == 'POST':
        try:
            kategori = request.form['kategori']
            batas = float(request.form['batas'])
            bulan = int(request.form['bulan'])
            tahun = int(request.form['tahun'])
            if not kategori or not batas or not bulan or not tahun:
                raise ValueError("Semua field wajib diisi.")
            anggaran_baru = {
                'kategori': kategori,
                'batas': batas,
                'bulan': bulan,
                'tahun': tahun
            }
            supabase.table('anggaran').insert(anggaran_baru).execute()
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Error inserting anggaran: {e}")
            return render_template('tambah_anggaran.html', error=str(e), kategori=KATEGORI_PENGELUARAN,
                                   current_year=datetime.now().year)
    return render_template('tambah_anggaran.html', kategori=KATEGORI_PENGELUARAN,
                           current_year=datetime.now().year)

@app.route('/tambah_tabungan', methods=['GET', 'POST'])
def tambah_tabungan():
    if request.method == 'POST':
        try:
            nama = request.form['nama']
            target = float(request.form['target'])
            tenggat = datetime.strptime(request.form['tenggat'], '%Y-%m-%d').date()
            tabungan_baru = {
                'nama': nama,
                'target': target,
                'terkumpul': 0.0,
                'tenggat': tenggat.isoformat()
            }
            supabase.table('tabungan').insert(tabungan_baru).execute()
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Error inserting tabungan: {e}")
            return render_template('tambah_tabungan.html', error=str(e))
    return render_template('tambah_tabungan.html')

@app.route('/tambah_dana_tabungan/<int:id>', methods=['POST'])
def tambah_dana_tabungan(id):
    try:
        jumlah = float(request.form['jumlah'])
        response = supabase.table('tabungan').select('terkumpul').eq('id', id).execute()
        terkumpul = float(response.data[0]['terkumpul']) + jumlah
        supabase.table('tabungan').update({'terkumpul': terkumpul}).eq('id', id).execute()
    except Exception as e:
        print(f"Error updating tabungan: {e}")
    return redirect(url_for('index'))

@app.route('/ekspor_excel')
def ekspor_excel():
    try:
        response = supabase.table('transaksi').select('*').execute()
        transaksi = response.data or []
    except Exception as e:
        print(f"Error fetching transaksi for export: {e}")
        transaksi = []
    data = [{
        'Tanggal': t['tanggal'],
        'Deskripsi': t['deskripsi'],
        'Jumlah': float(t['jumlah']),
        'Tipe': t['tipe'].capitalize(),
        'Kategori': t['kategori']
    } for t in transaksi]
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name='transaksi.xlsx', as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)