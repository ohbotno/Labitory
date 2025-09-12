#!/usr/bin/env python3
"""
Debug script to check foreign key constraints in SQLite database.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labitory.settings.development')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.db import connection

def check_foreign_keys():
    print("Checking foreign key constraints referencing booking_booking table...")
    
    with connection.cursor() as cursor:
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"Found {len(tables)} tables")
        
        # Check each table for foreign key references to booking_booking
        foreign_key_references = []
        
        for table in tables:
            try:
                cursor.execute(f"PRAGMA foreign_key_list({table})")
                foreign_keys = cursor.fetchall()
                
                for fk in foreign_keys:
                    # fk structure: (id, seq, table, from, to, on_update, on_delete, match)
                    if len(fk) >= 3 and fk[2] == 'booking_booking':
                        foreign_key_references.append({
                            'from_table': table,
                            'from_column': fk[3],
                            'to_table': fk[2],
                            'to_column': fk[4],
                            'on_delete': fk[6],
                        })
                        print(f"  {table}.{fk[3]} -> {fk[2]}.{fk[4]} (ON DELETE {fk[6]})")
            except Exception as e:
                print(f"Error checking table {table}: {e}")
        
        print(f"\nTotal foreign key references to booking_booking: {len(foreign_key_references)}")
        
        # Now check for any records that reference booking ID 1
        print(f"\nChecking for records referencing booking ID 1:")
        booking_id = 1
        
        for ref in foreign_key_references:
            try:
                table_name = ref['from_table']
                column_name = ref['from_column']
                
                query = f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = ?"
                cursor.execute(query, [booking_id])
                count = cursor.fetchone()[0]
                if count > 0:
                    print(f"  {table_name}.{column_name}: {count} records")
                    
                    # Show the actual records
                    query2 = f"SELECT * FROM {table_name} WHERE {column_name} = ? LIMIT 5"
                    cursor.execute(query2, [booking_id])
                    records = cursor.fetchall()
                    print(f"    Sample records: {records}")
            except Exception as e:
                print(f"  Error checking {ref['from_table']}.{ref['from_column']}: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    check_foreign_keys()