import sqlite3
from pathlib import Path
p = Path(r"C:\Users\小敏\PycharmProjects\SpiderAgent\helloagent\.edge-profile\Default\Network\Cookies")
con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
rows = con.execute("select host_key, count(*) from cookies group by host_key order by host_key").fetchall()
for host, count in rows:
    if any(x in host for x in ("taobao", "tmall", "jd.com", "yangkeduo", "pinduoduo")):
        print(host, count)
print("total", sum(c for h,c in rows))
con.close()
