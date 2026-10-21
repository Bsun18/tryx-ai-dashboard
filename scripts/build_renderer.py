"""Build the native DEX renderer with JDK 17 and Android SDK (no APK install)."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-root',default=os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT'))
    parser.add_argument('--java-home',default=os.environ.get('JAVA_HOME'))
    parser.add_argument('--platform',default='android-30')
    parser.add_argument('--build-tools-dir')
    args=parser.parse_args()
    if not args.sdk_root: parser.error('Set ANDROID_HOME or pass --sdk-root.')
    sdk=Path(args.sdk_root)
    android=sdk/'platforms'/args.platform/'android.jar'
    if not android.exists(): parser.error('Android platform not found: '+str(android))
    candidates=sorted((sdk/'build-tools').glob('*/lib/d8.jar'),key=lambda p:tuple(int(n) if n.isdigit() else 0 for n in p.parents[1].name.split('.')))
    d8=Path(args.build_tools_dir)/'lib'/'d8.jar' if args.build_tools_dir else candidates[-1] if candidates else None
    if not d8 or not d8.exists(): parser.error('Install Android SDK Build-Tools or pass --build-tools-dir.')
    suffix='.exe' if os.name=='nt' else ''
    java=str(Path(args.java_home)/'bin'/('java'+suffix)) if args.java_home else shutil.which('java')
    javac=str(Path(args.java_home)/'bin'/('javac'+suffix)) if args.java_home else shutil.which('javac')
    if not java or not javac: parser.error('JDK 17 is required. Set JAVA_HOME or --java-home.')
    build=ROOT/'build';build.mkdir(exist_ok=True)
    if not build.resolve().is_relative_to(ROOT.resolve()): raise ValueError('Build directory must remain inside this checkout.')
    with tempfile.TemporaryDirectory(prefix='renderer-',dir=build) as temporary:
        temp=Path(temporary);classes=temp/'classes';dex=temp/'dex'
        classes.mkdir();dex.mkdir()
        sources=sorted((ROOT/'renderer'/'src').glob('*.java'))
        subprocess.run([javac,'-encoding','UTF-8','-source','8','-target','8','-bootclasspath',str(android),'-d',str(classes),*map(str,sources)],check=True)
        subprocess.run([java,'-cp',str(d8),'com.android.tools.r8.D8','--lib',str(android),'--min-api','26','--output',str(dex),*map(str,sorted(classes.rglob('*.class')))],check=True)
        output=ROOT/'renderer'/'renderer.jar'
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            info=zipfile.ZipInfo('classes.dex',date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,(dex/'classes.dex').read_bytes())
        print('Built:',output)


if __name__=='__main__':main()
