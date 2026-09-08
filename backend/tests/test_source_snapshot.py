import json

import pytest

from backend.scripts import freeze_generation_source as snapshots


@pytest.fixture
def source(tmp_path):
    files = {'backend/__init__.py': '', 'backend/app/version.py': "COMPILER_VERSION = 'test'\n",
             'blender/nested/importer.py': '# source\n', 'docs/contract.json': '{}',
             'fixtures/audio/clip.mp3': 'audio sample'}
    for name,content in files.items():
        path = tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content,encoding='utf-8')
    return tmp_path, tmp_path/'fixtures/audio/clip.mp3'


def test_snapshot_binds_resources_and_is_reusable(source):
    root,audio = source
    first = snapshots.freeze(audio,root)
    assert snapshots.freeze(audio,root) == first
    metadata = snapshots.verify(first)
    assert 'blender/nested/importer.py' in metadata['files']
    (root/'docs/contract.json').write_text('{"changed": true}',encoding='utf-8')
    second = snapshots.freeze(audio,root)
    assert second != first
    assert snapshots.verify(first)['compiler_source_sha256'] == snapshots.verify(second)['compiler_source_sha256']
    (first/'docs/contract.json').write_text('changed after copy',encoding='utf-8')
    with pytest.raises(ValueError,match='Snapshot resource changed'):
        snapshots.verify(first)


def test_concurrent_edit_during_copy_rejects_snapshot(source,monkeypatch):
    root,audio = source
    copy = snapshots.shutil.copy2
    def changing_copy(src,dest):
        result = copy(src,dest)
        if src.name == 'contract.json':
            src.write_text('concurrent change',encoding='utf-8')
        return result
    monkeypatch.setattr(snapshots.shutil,'copy2',changing_copy)
    with pytest.raises(RuntimeError,match='changed during snapshot copy'):
        snapshots.freeze(audio,root)
    assert not list((root/'artifacts/model_versions/source_snapshots').glob('*/source_snapshot.json'))


def test_corpus_records_are_copied_and_hash_checked_before_generation(source):
    root,audio = source
    extra = root/'fixtures/audio/second.mp3'
    extra.write_bytes(b'different recording')
    corpus = root/'docs/corpus.json'
    tracks = [{'id':'second','local_path':str(extra),'sha256':snapshots.digest(extra),
               'counted_in_final_20':True},
              {'id':'auxiliary','local_path':'missing-file','counted_in_final_20':False}]
    corpus.write_text(json.dumps({'tracks':tracks}))
    fixed = snapshots.freeze(audio,root,corpus_path=corpus)
    assert snapshots.verify(fixed)['corpus_inputs']=={'second':'fixtures/audio/second.mp3'}
    assert (fixed/'fixtures/audio/second.mp3').read_bytes()==extra.read_bytes()
    extra.write_bytes(b'changed recording')
    with pytest.raises(ValueError,match='recording hash changed'):
        snapshots.freeze(audio,root,corpus_path=corpus)
