import csv
import pymysql
import os
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Lucky@2005',
    'database': 'ecommerce',
    'charset': 'utf8mb4',
    'use_unicode': True
}

# CSV files configuration
csv_files = [
    ('customers.csv', 'customers'),
    ('orders.csv', 'orders'),
    ('sellers.csv', 'sellers'),
    ('products.csv', 'products'),
    ('geolocation.csv', 'geolocation'),
    ('payments.csv', 'payments'),
    ('order_items.csv', 'order_items')
]

folder_path = 'D:/Data_Analyst/Dataset'

def create_connection():
    """Create database connection"""
    try:
        print("🔌 Attempting to connect to MySQL database...")
        connection = pymysql.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            charset=DB_CONFIG['charset']
        )
        print("✅ Database connection established successfully")
        return connection
    except Exception as e:
        print(f"❌ Error creating database connection: {e}")
        return None

def get_sql_type(value, max_length=0):
    """Determine SQL data type based on value with better handling"""
    if not value or value.strip() == '':
        return 'VARCHAR(255)'
    
    value_str = str(value).strip()
    
    # Check for numeric values
    if value_str.replace('.', '').replace('-', '').replace('+', '').isdigit():
        if '.' in value_str:
            return 'DECIMAL(20,6)'
        else:
            return 'BIGINT'
    
    # For text fields, use more generous sizing
    if max_length > 1000:
        return 'TEXT'
    elif max_length > 500:
        return 'VARCHAR(1000)'
    elif max_length > 255:
        return 'VARCHAR(500)'
    else:
        # Use at least 3x the max length found, minimum 100
        safe_length = max(max_length * 3, 100, len(value_str) * 2)
        return f'VARCHAR({min(safe_length, 1000)})'

def create_table_from_csv(csv_file, table_name, connection):
    """Create table structure with better data type detection"""
    try:
        file_path = os.path.join(folder_path, csv_file)
        
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            headers = next(reader)
            
            # Sample more rows for better type detection
            sample_rows = []
            for i, row in enumerate(reader):
                sample_rows.append(row)
                if i >= 100:  # Sample first 100 rows
                    break
        
        # Determine column types with better logic
        columns = []
        for i, header in enumerate(headers):
            col_name = header.replace(' ', '_').replace('-', '_').replace('.', '_').replace('(', '').replace(')', '')
            
            # Get sample values for this column
            sample_values = []
            max_length = 0
            
            for row in sample_rows:
                if i < len(row) and row[i].strip():
                    val = row[i].strip()
                    sample_values.append(val)
                    max_length = max(max_length, len(val))
            
            if sample_values:
                # Check if all numeric
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
                    if has_decimal:
                        col_type = 'DECIMAL(20,6)'
                    else:
                        col_type = 'BIGINT'
                else:
                    # Text field - be more generous with sizing
                    if max_length > 1000:
                        col_type = 'TEXT'
                    else:
                        # Use generous VARCHAR size
                        safe_size = max(max_length * 4, 200)
                        col_type = f'VARCHAR({min(safe_size, 2000)})'
            else:
                col_type = 'VARCHAR(500)'
            
            columns.append(f"`{col_name}` {col_type}")
        
        # Drop table if exists and create new one
        cursor = connection.cursor()
        cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        
        create_sql = f"CREATE TABLE `{table_name}` ({', '.join(columns)})"
        cursor.execute(create_sql)
        connection.commit()
        
        print(f"✅ Table '{table_name}' created successfully")
        return headers
        
    except Exception as e:
        print(f"❌ Error creating table {table_name}: {e}")
        return None

def load_csv_to_mysql(csv_file, table_name, connection):
    """Load CSV file data into MySQL table with better error handling"""
    try:
        file_path = os.path.join(folder_path, csv_file)
        
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return False
        
        print(f"📖 Reading {csv_file}...")
        
        # Create table structure
        headers = create_table_from_csv(csv_file, table_name, connection)
        if not headers:
            return False
        
        # Load data with better error handling
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
                    # Clean and prepare row data
                    clean_row = []
                    for i, value in enumerate(row):
                        if i >= len(headers):
                            break
                        
                        # Clean the value
                        clean_value = str(value).strip() if value else ''
                        
                        # Handle empty numeric fields
                        if clean_value == '':
                            clean_value = None
                        
                        clean_row.append(clean_value)
                    
                    # Pad row if it has fewer columns than headers
                    while len(clean_row) < len(headers):
                        clean_row.append(None)
                    
                    batch_data.append(clean_row)
                    row_count += 1
                    
                    if len(batch_data) >= batch_size:
                        try:
                            cursor.executemany(insert_sql, batch_data)
                            connection.commit()
                            print(f"  ⬆️  Loaded {row_count} rows...")
                        except Exception as batch_error:
                            # Try inserting rows one by one to identify problematic rows
                            for single_row in batch_data:
                                try:
                                    cursor.execute(insert_sql, single_row)
                                    connection.commit()
                                except Exception:
                                    error_count += 1
                            print(f"  ⚠️  Loaded {row_count} rows (with {error_count} errors)...")
                        
                        batch_data = []
                
                except Exception as row_error:
                    error_count += 1
                    continue
            
            # Insert remaining data
            if batch_data:
                try:
                    cursor.executemany(insert_sql, batch_data)
                    connection.commit()
                except Exception:
                    # Insert remaining rows one by one
                    for single_row in batch_data:
                        try:
                            cursor.execute(insert_sql, single_row)
                            connection.commit()
                        except Exception:
                            error_count += 1
        
        if error_count > 0:
            print(f"✅ Successfully loaded {row_count - error_count} rows into '{table_name}' table (skipped {error_count} problematic rows)")
        else:
            print(f"✅ Successfully loaded {row_count} rows into '{table_name}' table")
        return True
        
    except Exception as e:
        print(f"❌ Error loading {csv_file} into {table_name}: {e}")
        return False

def main():
    """Main function to process all CSV files"""
    print("🚀 Starting CSV to MySQL import process...")
    print(f"📁 Source folder: {folder_path}")
    print(f"🗄️  Target database: {DB_CONFIG['database']}")
    print("=" * 60)
    
    if not os.path.exists(folder_path):
        print(f"❌ Source folder not found: {folder_path}")
        sys.exit(1)
    
    connection = create_connection()
    if not connection:
        print("❌ Failed to create database connection. Exiting...")
        sys.exit(1)
    
    successful_loads = 0
    failed_loads = 0
    
    try:
        for i, (csv_file, table_name) in enumerate(csv_files, 1):
            print(f"\n[{i}/{len(csv_files)}] Processing {csv_file} -> {table_name}")
            print("-" * 50)
            
            success = load_csv_to_mysql(csv_file, table_name, connection)
            
            if success:
                successful_loads += 1
            else:
                failed_loads += 1
        
        print("\n" + "=" * 60)
        print("📊 FINAL SUMMARY")
        print("=" * 60)
        print(f"✅ Successfully loaded: {successful_loads} files")
        print(f"❌ Failed to load: {failed_loads} files")
        print(f"📁 Total files processed: {len(csv_files)}")
        
        if successful_loads == len(csv_files):
            print("🎉 All files loaded successfully!")
        elif successful_loads > 0:
            print("⚠️  Some files loaded successfully, check errors above")
        else:
            print("💥 No files were loaded successfully")
            
    finally:
        connection.close()
        print("🔌 Database connection closed")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️  Process interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
    finally:
        print("🏁 Script execution completed")