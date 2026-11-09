import sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'darkwolf-backend'))
from selenium.common.exceptions import TimeoutException,WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from app.core.config import settings
from app.sites.html_leak_sites.collector import _make_driver,_challenge
sites=[('Blackout Ransomware','http://black3gnkizshuynieigw6ejgpblb53mpasftzd6pydqpmq2vn2xf6yd.onion/'),('BlackX','http://blackxppq2jvqyg4slyg3sbszv7ib2avaaycvhff5qipgdoepqi57xyd.onion/'),('SETTRA','http://settra5ldqwgtw5q7z5awbsvlksakyfojuc5slgrz5lvapune4fantqd.onion/'),('Majinahanashi','http://lthicpjqc7gkn5eq3epxndc2uig3yngvcbdya4u3m3byjod5km4yuwqd.onion/#blog')]
driver=_make_driver(settings.tor_host,settings.tor_socks_port);driver.set_page_load_timeout(20);out=[]
try:
 for name,url in sites:
  try:
   try: driver.get(url)
   except TimeoutException: pass
   WebDriverWait(driver,20).until(lambda d:d.execute_script('return document.readyState') in ('interactive','complete'))
   gate=_challenge(driver,name.casefold().replace(' ','_'))
   row={'group':name,'current_url':driver.current_url,'status':'captcha_or_antibot' if gate else 'accessible','gate':gate,'title':driver.title}
  except Exception as exc: row={'group':name,'status':'inaccessible','gate':None,'error':f'{type(exc).__name__}: {str(exc)[:220]}'}
  out.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
finally:driver.quit()
with (ROOT/'browser_gate_recheck_2026-10-17.json').open('w',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
