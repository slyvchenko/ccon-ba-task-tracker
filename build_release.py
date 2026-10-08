"""Build a source-only ZIP from the checked-in manifest, without runtime data."""
import argparse
import json
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app_config import ROOT
from pipeline_lock import replace_file


def release_files(root=ROOT):
    root = Path(root).resolve()
    names = json.loads((root / 'release_manifest.json').read_text(encoding='utf-8'))
    if not isinstance(names, list) or not names or not all(isinstance(name, str) for name in names) or len(set(names)) != len(names):
        raise ValueError('Release manifest must contain unique source paths.')
    paths = []
    for name in names:
        if not isinstance(name, str):
            raise ValueError('Release paths must be text.')
        path = (root / name).resolve()
        if (Path(name).is_absolute() or '..' in Path(name).parts or not path.is_relative_to(root)
                or not path.is_file()):
            raise ValueError('Missing or invalid release source: ' + name)
        paths.append((name, path))
    return paths


def build_release(output, root=ROOT):
    paths = release_files(root)  # Fail before touching an existing ZIP.
    output = Path(output).resolve()
    if output.suffix.lower() != '.zip':
        raise ValueError('Release output must be a ZIP file.')
    if any(output == source for _, source in paths):
        raise ValueError('Output must not overwrite a release source.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        with ZipFile(temporary, 'x', ZIP_DEFLATED) as archive:
            for name, source in paths:
                archive.write(source, 'ccon-ba-desk/' + name)
        with ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Release ZIP verification failed.')
        replace_file(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build_release(args.output))


if __name__ == '__main__':
    main()
