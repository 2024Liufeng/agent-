"""将试采样本写入指定 MySQL，保留逐条结果和地区来源。"""
import datetime
import html
import os
import re
from pathlib import Path

from . import storage

MAPPING = {
    "bid_ann": (0, 0), "bid_candidate": (5, 1), "bid_result": (5, 1),
    "bid_change": (3, 0), "bid_termination": (3, 0),
    "nonbid_compare": (4, 2), "nonbid_bidding": (4, 2),
    "nonbid_change": (3, 2), "nonbid_termination": (3, 2),
}
PROVINCES = ["北京市", "天津市", "上海市", "重庆市", "河北省", "山西省", "辽宁省", "吉林省", "黑龙江省", "江苏省", "浙江省", "安徽省", "福建省", "江西省", "山东省", "河南省", "湖北省", "湖南省", "广东省", "海南省", "四川省", "贵州省", "云南省", "陕西省", "甘肃省", "青海省", "台湾省", "内蒙古自治区", "广西壮族自治区", "西藏自治区", "宁夏回族自治区", "新疆维吾尔自治区"]


def region(content):
    text = re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]*>", " ", content)))
    # 截取招标人字段和紧随其后的地址，遇到代理机构即停止。
    for m in re.finditer(r"(?<!代理)(?:招标人|采购人)[:：]", text):
        following = text[m.end():m.end() + 350]
        stop = re.search(r"(?:招标代理机构|采购商务代理|采购人商务代理|招标人商务代理|代理机构|联系人|电话|邮箱|二、)", following)
        section = following[:stop.start()] if stop else following
        name = re.split(r"地址[:：]", section, maxsplit=1)[0][:100]
        candidates = [("招标人名称", name)]
        address = re.search(r"地址[:：]([^：:]{1,150})", section)
        if address:
            candidates.append(("招标人地址", address.group(1)))
        for source, candidate in candidates:
            for province in PROVINCES:
                short = province[:2] if province in ("北京市", "天津市", "上海市", "重庆市") else province
                if short in candidate:
                    tail = candidate.split(short, 1)[1]
                    match = re.search(r"(雄安新区|两江新区|[\u4e00-\u9fff]{2,7}?(?:市|自治州|地区|盟))", tail)
                    city = match.group(1) if match and province not in ("北京市", "天津市", "上海市", "重庆市") else province
                    return province, city, source
    return "北京市", "北京市", "按原业务资料兜底，需人工核对"


def prepare(item):
    errors = item.get("validation_errors") or []
    if errors:
        raise ValueError("基础字段校验未通过")
    column = item.get("column_id")
    if column not in MAPPING:
        raise ValueError("栏目分类尚未映射")
    # 易联 competeList 的实测首条为谈判公告，不能当作竞价公告写库。
    if column == "nonbid_bidding" and "竞价" not in item.get("title", ""):
        raise ValueError("候选竞价接口样本标题与栏目不一致，需人工确认")
    title = item.get("title", "").strip()
    if not title or len(title) > 500:
        raise ValueError("标题为空或超长")
    try:
        release_time = datetime.datetime.strptime(item["release_time"], "%Y-%m-%d %H:%M:%S")
    except (KeyError, ValueError):
        raise ValueError("发布时间格式不正确") from None
    if len(item.get("from_site", "")) > 255 or len(item.get("collect_id", "")) > 1500:
        raise ValueError("来源链接超长")
    province, city, method = region(item["content"])
    content = re.sub(r"font-family\s*:\s*[^;\"'}]+", "font-family: SimSun", item["content"], flags=re.I)
    content = re.sub(r"font-size\s*:\s*[^;\"'}]+", "font-size: 16px", content, flags=re.I)
    content = re.sub(r"font-weight\s*:\s*(?:bold|bolder|[5-9]00)", "font-weight: normal", content, flags=re.I)
    ann, category = MAPPING[column]
    return {"title": title, "release_time": release_time, "announcement_type": ann, "type": category,
            "province": province, "city": city, "region_source": method, "content": content,
            "collect_id": item["collect_id"], "from_site": item["from_site"], "column_id": column}


def connection_config():
    keys = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise ValueError("缺少数据库环境变量：" + ", ".join(missing))
    return {"host": os.environ["DB_HOST"], "user": os.environ["DB_USER"], "password": os.environ["DB_PASSWORD"], "database": os.environ["DB_NAME"], "port": int(os.getenv("DB_PORT", "3306")), "charset": "utf8mb4", "connect_timeout": 15, "read_timeout": 90, "autocommit": False}


def stage(run_id, connect=None):
    path = storage.run_path(run_id)
    report = storage.read(path / "report.json")
    for name in ("config", "samples"):
        if report.get(name + "_sha256") != storage.digest(path / (name + ".json")):
            raise ValueError(f"{name} 在试采后已变化，请重新试采")
    if report.get("run_id") != run_id:
        raise ValueError("任务编号与报告不一致")
    config = connection_config()
    if connect is None:
        try:
            import pymysql
        except ImportError:
            raise ValueError("请先安装依赖：pip install -r requirements.txt") from None
        connect = pymysql.connect
    candidates, skipped = [], []
    for item in storage.read(path / "samples.json"):
        try:
            candidates.append(prepare(item))
        except (ValueError, TypeError, KeyError) as exc:
            skipped.append({"column_id": item.get("column_id"), "title": item.get("title"), "reason": str(exc)})
    conn = connect(**config)
    inserted, duplicates = [], []
    try:
        with conn.cursor() as cur:
            for item in candidates:
                cur.execute("SELECT id FROM business_invite_tenders WHERE title=%s AND release_time=%s LIMIT 1", (item["title"], item["release_time"]))
                existing = cur.fetchone()
                if existing:
                    duplicates.append({"title": item["title"], "id": existing[0]})
                    continue
                now = datetime.datetime.now()
                cur.execute("""INSERT INTO business_invite_tenders
                    (title, announcement_type, creator_name, city, province, content, type,
                     is_public_bidding, is_examine, is_international, collect_id, from_site,
                     create_time, update_time, release_time, gather)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,1,0,0,%s,%s,%s,%s,%s,1)""",
                    (item["title"], item["announcement_type"], "柳风", item["city"], item["province"], item["content"], item["type"], item["collect_id"], item["from_site"], now, now, item["release_time"]))
                inserted.append({k: item[k] for k in ("title", "column_id", "province", "city", "region_source", "collect_id")})
                inserted[-1]["id"] = cur.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        storage.event(path, run_id, "trial_database", "failed")
        raise
    finally:
        conn.close()
    result = {"at": storage.now(), "database": config["database"], "table": "business_invite_tenders", "inserted": inserted, "duplicates": duplicates, "skipped": skipped,
              "note": "试采样本已写库供审核；地区兜底和栏目分类需甲方核对。重复判定按标题和发布时间。"}
    filename = "database-stage-" + storage.now().replace(":", "-").replace("+", "_") + ".json"
    storage.save(path / filename, result)
    storage.event(path, run_id, "trial_database", "success", inserted=len(inserted), duplicates=len(duplicates), skipped=len(skipped))
    return path / filename, result
