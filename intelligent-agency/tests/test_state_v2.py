import os, sys, time
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src'))
from agency.state import StateStore
from agency.github_worker import GitHubGuard, ReviewChangeSet, FileChange


def test_queue_claim_complete(tmp_path):
    s=StateStore(str(tmp_path/'h.db')); ident=s.enqueue('scan',{'x':1})
    item=s.claim('w1'); assert item['id']==ident and item['payload']['x']==1
    s.complete(ident); assert s.db.execute('select status from work_items where id=?',(ident,)).fetchone()['status']=='done'


def test_memory_requires_explicit_status(tmp_path):
    s=StateStore(str(tmp_path/'h.db')); s.remember('a','project/x',{'fact':'candidate'},provenance='test')
    assert s.recall(scope='project/x')[0]['status']=='candidate'


def test_budget_limit(tmp_path):
    s=StateStore(str(tmp_path/'h.db')); assert s.charge('today',1,2); assert s.charge('today',1,2); assert not s.charge('today',1,2)


def test_guard_allows_horizon_branch():
    GitHubGuard.validate(ReviewChangeSet('t','horizon/improve-x','s',[FileChange('src/x.py','x=1','m')]))


def test_guard_blocks_main_and_workflow_changes():
    with pytest.raises(PermissionError): GitHubGuard.validate(ReviewChangeSet('t','main','s'))
    with pytest.raises(PermissionError): GitHubGuard.validate(ReviewChangeSet('t','horizon/x','s',[FileChange('.github/workflows/x.yml','x','m')]))
