from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
names=['account_flow_test.py','imagegen_fakeflow.py','imagegen_test_flow.py','imagegen_test_queue.py','integration_test_pipeline.py']
dest=ROOT/'dist/_cache/before-library-mode/tests'
dest.mkdir(parents=True,exist_ok=True)
for name in names:
    source=ROOT/'tests'/name
    if source.exists():shutil.move(str(source),str(dest/name))
print('Archived tests for retired image generation; new asset library tests replace them.')
