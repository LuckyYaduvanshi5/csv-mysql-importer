from flask import Flask, request, jsonify, render_template, session, send_from_directory
from flask_socketio import SocketIO, emit
import csv
import pymysql
import os
import threading
import time
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'csv-mysql-importer-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Use threading instead of eventlet for Python 3.13 compatibility
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test-connection', methods=['POST'])
def test_connection():
    try:
        data = request.json
        connection = pymysql.connect(
            host=data['host'],
            user=data['user'],
            password=data['password'],
            database=data['database'],
            charset=data.get('charset', 'utf8mb4')
        )
        connection.close()
        return jsonify({'success': True, 'message': 'Connection successful!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/upload-files', methods=['POST'])
def upload_files():
    try:
        if 'files' not in request.files:
            return jsonify({'success': False, 'message': 'No files selected'})
        
        files = request.files.getlist('files')
        uploaded_files = []
        
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                uploaded_files.append({
                    'filename': filename,
                    'path': file_path,
                    'table_name': filename.rsplit('.', 1)[0]
                })
        
        session['uploaded_files'] = uploaded_files
        return jsonify({'success': True, 'files': uploaded_files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def create_table_from_csv(file_path, table_name, connection, socket_id):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            headers = next(reader)
            
            sample_rows = []
            for i, row in enumerate(reader):
                sample_rows.append(row)
                if i >= 100:
                    break
        
        columns = []
        for i, header in enumerate(headers):
            col_name = header.replace(' ', '_').replace('-', '_').replace('.', '_').replace('(', '').replace(')', '')
            
            sample_values = []
            max_length = 0
            
            for row in sample_rows:
                if i < len(row) and row[i].strip():
                    val = row[i].strip()
                    sample_values.append(val)
                    max_length = max(max_length, len(val))
            
            if sample_values:
                all_numeric = True
                has_decimal = False
                
                for val in sample_values:
                    clean_val = val.replace('.', '').replace('-', '').replace('+', '')
                    if not clean_val.isdigit():
                        all_numeric = False
                        break
                    if '.' in val:
                        has_decimal = True
                
                if all_numeric:
                    col_type = 'DECIMAL(20,6)' if has_decimal else 'BIGINT'
                else:
                    if max_length > 1000:
                        col_type = 'TEXT'
                    else:
                        safe_size = max(max_length * 4, 200)
                        col_type = f'VARCHAR({min(safe_size, 2000)})'
            else:
                col_type = 'VARCHAR(500)'
            
            columns.append(f"`{col_name}` {col_type}")
        
        cursor = connection.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        
        create_sql = f"CREATE TABLE `{table_name}` ({', '.join(columns)})"
        cursor.execute(create_sql)
        connection.commit()
        
        socketio.emit('table_created', {'table_name': table_name}, room=socket_id)
        return headers
        
    except Exception as e:
        socketio.emit('error', {'message': f'Error creating table {table_name}: {str(e)}'}, room=socket_id)
        return None

def import_csv_data(file_path, table_name, headers, connection, socket_id):
    try:
        cursor = connection.cursor()
        row_count = 0
        error_count = 0
        
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            
            placeholders = ', '.join(['%s'] * len(headers))
            insert_sql = f"INSERT INTO `{table_name}` VALUES ({placeholders})"
            
            batch_size = 1000
            batch_data = []
            
            for row in reader:
                try:
                    clean_row = []
                    for i, value in enumerate(row):
                        if i >= len(headers):
                            break
                        clean_value = str(value).strip() if value else None
                        clean_row.append(clean_value)
                    
                    while len(clean_row) < len(headers):
                        clean_row.append(None)
                    
                    batch_data.append(clean_row)
                    row_count += 1
                    
                    if len(batch_data) >= batch_size:
                        try:
                            cursor.executemany(insert_sql, batch_data)
                            connection.commit()
                            socketio.emit('progress', {
                                'table_name': table_name,
                                'rows_loaded': row_count,
                                'errors': error_count
                            }, room=socket_id)
                        except Exception:
                            for single_row in batch_data:
                                try:
                                    cursor.execute(insert_sql, single_row)
                                    connection.commit()
                                except Exception:
                                    error_count += 1
                        
                        batch_data = []
                
                except Exception:
                    error_count += 1
                    continue
            
            if batch_data:
                try:
                    cursor.executemany(insert_sql, batch_data)
                    connection.commit()
                except Exception:
                    for single_row in batch_data:
                        try:
                            cursor.execute(insert_sql, single_row)
                            connection.commit()
                        except Exception:
                            error_count += 1
        
        socketio.emit('file_completed', {
            'table_name': table_name,
            'total_rows': row_count - error_count,
            'errors': error_count
        }, room=socket_id)
        
        return True
        
    except Exception as e:
        socketio.emit('error', {'message': f'Error importing {table_name}: {str(e)}'}, room=socket_id)
        return False

@socketio.on('start_import')
def handle_import(data):
    socket_id = request.sid
    
    try:
        # Connect to database
        connection = pymysql.connect(
            host=data['host'],
            user=data['user'],
            password=data['password'],
            database=data['database'],
            charset=data.get('charset', 'utf8mb4')
        )
        
        emit('import_started', {'message': 'Import process started'})
        
        files_to_process = data['files']
        successful_files = 0
        failed_files = 0
        
        for i, file_info in enumerate(files_to_process):
            emit('file_started', {
                'filename': file_info['filename'],
                'table_name': file_info['table_name'],
                'current': i + 1,
                'total': len(files_to_process)
            })
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_info['filename'])
            
            # Create table
            headers = create_table_from_csv(file_path, file_info['table_name'], connection, socket_id)
            
            if headers:
                # Import data
                success = import_csv_data(file_path, file_info['table_name'], headers, connection, socket_id)
                if success:
                    successful_files += 1
                else:
                    failed_files += 1
            else:
                failed_files += 1
        
        emit('import_completed', {
            'successful': successful_files,
            'failed': failed_files,
            'total': len(files_to_process)
        })
        
        connection.close()
        
    except Exception as e:
        emit('error', {'message': str(e)})

@app.route('/robots.txt')
def robots_txt():
    return send_from_directory(app.static_folder, 'robots.txt')

@app.route('/sitemap.xml')
def sitemap_xml():
    return send_from_directory(app.static_folder, 'sitemap.xml')

@app.after_request
def after_request(response):
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Cache headers for static files
    if request.endpoint and 'static' in request.endpoint:
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    
    return response

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
