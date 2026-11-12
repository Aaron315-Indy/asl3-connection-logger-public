from io import BytesIO
import pytest

from asl3_connection_logger.local_nodes import configured_nodes
from asl3_connection_logger.web import DashboardHandler


def test_local_sections_and_includes_only(tmp_path):
    config = tmp_path / 'rpt.conf'
    config.write_text('[900]\n[20](base) ; local\n[nodes]\n1 = remote\n[2](base, !)\n#include "extra.conf"\n')
    (tmp_path / 'extra.conf').write_text('[100]\n[20]\n#include rpt.conf\n')
    assert configured_nodes(config) == ['20', '100', '900']


def test_missing_config_has_no_invented_default(tmp_path):
    assert configured_nodes(tmp_path / 'missing') == []


@pytest.mark.parametrize('sections, expected', [
    ('[658860]\n[20]\n[2001]\n[1999]\n', '2001'),
    ('[0]\n[20]\n[1999]\n', ''),
    ('[1999]\n[2000]\n[2001]\n', '2000'),
    ('[1999]\n', ''),
    ('[01999]\n[02000]\n[2001]\n', '02000'),
    ('[10000]\n[9999]\n', '9999'),
    ('', ''),
    (None, ''),
])
def test_homepage_populates_eligible_default_before_script(tmp_path, sections, expected):
    config = tmp_path / 'rpt.conf'
    if sections is not None:
        config.write_text(sections)
    handler = object.__new__(DashboardHandler)
    handler.rpt_config = config
    handler.wfile = BytesIO()
    handler.send_response = lambda *args: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.send_homepage()
    page = handler.wfile.getvalue().decode()
    assert f'<input id="node" value="{expected}" placeholder="All nodes"' in page
    assert page.index(f'<input id="node" value="{expected}"') < page.index('load();')
    assert '{{DEFAULT_LOCAL_NODE}}' not in page
    # Refresh reads the current field and leaves an empty filter unset.
    assert 'if (el(key).value.trim()) query.set(key, el(key).value.trim())' in page


@pytest.mark.parametrize('private', ['0', '1999'])
def test_manual_filter_and_clearing_include_private_local_nodes(tmp_path, private):
    from asl3_connection_logger.collector import process_event
    from asl3_connection_logger.web import read_dashboard
    db = tmp_path / 'history.db'
    process_event(db, private, '1', 'connect')
    process_event(db, '2000', '1999', 'connect')
    result = read_dashboard(db, node=private)
    assert [row['local_node'] for row in result['sessions']] == [private]
    assert result['counts']['active'] == 1
    assert {row['local_node'] for row in read_dashboard(db, node='')['sessions']} == {private, '2000'}
    assert read_dashboard(db, remote='1999')['sessions'][0]['local_node'] == '2000'


def test_default_uses_public_nodes_from_includes_without_removing_private_nodes(tmp_path):
    config = tmp_path / 'rpt.conf'
    config.write_text('[0]\n[1999]\n[658860]\n#include "extra.conf"\n')
    (tmp_path / 'extra.conf').write_text('[3000]\n#tryinclude "nodes-*.conf"\n#include rpt.conf\n')
    (tmp_path / 'nodes-public.conf').write_text('[2000](base)\n[2500](!)\n[nodes]\n2 = remote\n')
    assert configured_nodes(config) == ['0', '1999', '2000', '3000', '658860']
    handler = object.__new__(DashboardHandler)
    handler.rpt_config = config
    handler.wfile = BytesIO()
    handler.send_response = lambda *args: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.send_homepage()
    assert '<input id="node" value="2000" placeholder="All nodes"' in handler.wfile.getvalue().decode()
