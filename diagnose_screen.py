"""Read basic ADB display capabilities without deploying or changing a screen."""
import json
import re

from settings import RUNTIME, find_adb, load_config, parse_devices, run_adb


def inspect_screens(config=None):
    adb=find_adb(load_config() if config is None else config)
    listed=run_adb(adb,'devices','-l')
    if listed.returncode: raise RuntimeError('ADB device discovery failed.')
    report={'format_version':1,'read_only':True,'devices':[]}
    for index,device in enumerate(parse_devices(listed.stdout),1):
        # Serial is only used to target commands. Never serialize it or raw logs.
        serial=device['serial']
        def property(name):
            result=run_adb(adb,'-s',serial,'shell','getprop',name)
            return result.stdout.strip() if result.returncode==0 else None
        model=property('ro.product.model')
        size=run_adb(adb,'-s',serial,'shell','wm','size')
        dimensions=re.findall(r'(\d+)x(\d+)',size.stdout) if size.returncode==0 else []
        resolution=list(map(int,dimensions[-1])) if dimensions else None
        report['devices'].append({'index':index,'model':model,'manufacturer':property('ro.product.manufacturer'),
            'android_release':property('ro.build.version.release'),'api_level':property('ro.build.version.sdk'),
            'effective_resolution':resolution,
            'matches_current_profile':bool(model and model.casefold()=='cm01_se' and resolution==[2240,1080])})
    return report


def main():
    report=inspect_screens()
    RUNTIME.mkdir(exist_ok=True)
    (RUNTIME/'screen-diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))
    print('Saved runtime/screen-diagnostic.json. No screen contents were changed.')


if __name__=='__main__': main()
