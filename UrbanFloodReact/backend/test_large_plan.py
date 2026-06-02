#!/usr/bin/env python
"""Test large evacuation plan storage"""

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

from dotenv import load_dotenv
from pathlib import Path
import os
import sys

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

import db

print('\nTesting large evacuation plan storage...')
large_plan = [{'route': i, 'nodes': list(range(100))} for i in range(500)]
print('  Created plan with {} routes'.format(len(large_plan)))

try:
    db.set_mcp_state(
        summary_data={'total': 5000},
        evacuation_plan=large_plan,
        hobli='test-hobli'
    )
    print('  [OK] Plan saved successfully (separate collection)')
    
    state = db.get_mcp_state()
    print('  [OK] Retrieved state')
    plan = state.get('evacuation_plan') or []
    print('  [OK] Evacuation plan has {} routes'.format(len(plan)))
    
    if len(plan) == len(large_plan):
        print('\n[SUCCESS] BSON limit fix verified - large plans now work!')
        sys.exit(0)
    else:
        print('\n[FAILED] Plan size mismatch: expected {}, got {}'.format(len(large_plan), len(plan)))
        sys.exit(1)
except Exception as e:
    print('\n[ERROR] {}'.format(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)
