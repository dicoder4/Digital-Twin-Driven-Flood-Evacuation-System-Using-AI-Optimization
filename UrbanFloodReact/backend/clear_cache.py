#!/usr/bin/env python
"""Clear MongoDB cache collections for clean retest"""

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

from dotenv import load_dotenv
from pathlib import Path
import os

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

import db

print('\nClearing MongoDB cache collections...\n')

# Get the database
mongo_db = db._get_db()
if mongo_db is None:
    print('❌ Failed to connect to MongoDB')
    exit(1)

collections_to_clear = [
    'region_cache',
    'shelter_cache', 
    'dem_cache',
    'mcp_state',
    'evacuation_plans',
]

for col_name in collections_to_clear:
    col = mongo_db[col_name]
    count = col.count_documents({})
    if count > 0:
        col.delete_many({})
        print(f'✓ Cleared {col_name}: deleted {count} document(s)')
    else:
        print(f'- {col_name}: already empty')

print('\n✅ All cache collections cleared!\n')
