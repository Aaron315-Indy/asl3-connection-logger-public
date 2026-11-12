from io import BytesIO
from pathlib import Path

from asl3_connection_logger.local_nodes import configured_nodes
from asl3_connection_logger.web import DashboardHandler


def test_local_sections_and_includes_only(tmp_path):
    config = tmp_path / 'rpt.conf'
    config.write_text('[900]\n[20](base) ; local\n[nodes]\n1 = remote\n[2](base, !)\n#include "extra.conf"\n')
    (tmp_path / 'extra.conf').write_text('[100]\n[20]\n#include rpt.conf\n')
    assert configured_nodes(config) == ['20', '100', '900']


def test_missing_config_has_no_invented_default(tmp_path):
    assert configured_nodes(tmp_path / 'missing') == []


def test_homepage_populates_value_before_script(tmp_path):
    config = tmp_path / 'rpt.conf'
    config.write_text('[900]\n[20]\n')
    handler = object.__new__(DashboardHandler)
    handler.rpt_config = config
    handler.wfile = BytesIO()
    handler.send_response = lambda *args: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.send_homepage()
    page = handler.wfile.getvalue().decode()
    assert '<input id="node" value="20" placeholder="All nodes"' in page
    assert page.index('value="20"') < page.index('load();')
    assert '{{DEFAULT_LOCAL_NODE}}' not in page
    # Refresh reads the current field and leaves an empty filter unset.
    assert 'if (el(key).value.trim()) query.set(key, el(key).value.trim())' in page


def test_manual_filter_and_clearing_include_other_local_nodes(tmp_path):
    from asl3_connection_logger.collector import process_event
    from asl3_connection_logger.web import read_dashboard
    db = tmp_path / 'history.db'
    process_event(db, '20', '1', 'connect')
    process_event(db, '900', '2', 'connect')
    assert [row['local_node'] for row in read_dashboard(db, node='900')['sessions']] == ['900']
    assert {row['local_node'] for row in read_dashboard(db, node='')['sessions']} == {'20', '900'}
