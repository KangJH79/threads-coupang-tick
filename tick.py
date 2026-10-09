"""PC 없이 1시간 1개 발행 — 비공개 저장소(threads-coupang)의 대기열을 보고 발행할 차례면 publish.yml 을 깨운다.
tick.yml 이 5분마다(회차가 끝날 때 다음 회차를 직접 부르는 사슬) 실행한다.
간격(60분+1분)·시간대·한 시간 1개·API 막힘 판단은 비공개 저장소의 tc/common.py publish_due 를 그대로 받아 쓴다.
다음 회차까지 기다릴 환경(wait1~5/wait30/wait60/wait240)을 GITHUB_OUTPUT 의 next 로 넘긴다.
★2026-10-09 두 번째 계정(@wol1000man) — 같은 저장소의 accounts/wol 칸도 본다(차례면 publish.yml -f account=wol).
  계정마다 따로 판단해야 해서(common 이 불러올 때 계정 폴더를 정함) 계정별로 작은 확인 스크립트를 따로 돌린다."""
import os, sys, json, math, subprocess, datetime as dt

R = os.environ.get("R", "KangJH79/threads-coupang")
OUT = os.environ.get("GITHUB_OUTPUT")
BUSY = ("queued", "in_progress", "waiting", "pending", "requested")
ACCOUNTS = [("", ""), ("wol", "accounts/wol")]   # (publish.yml account 입력, 저장소 안 폴더)
CHECK = r'''
import os, sys, json
sys.path.insert(0, os.path.abspath("w/tc"))
import common
q = json.load(open(common.QUEUE, encoding="utf-8")) if os.path.exists(common.QUEUE) else []
due = getattr(common, "next_due_time", lambda q: None)(q)
hours = common.publish_hours() if hasattr(common, "publish_hours") else (common.config().get("publish_hours") or list(range(10, 20)))
print(json.dumps({"why": common.publish_due(q), "due": due.isoformat() if due else None, "hours": hours}))
'''


def gh(*a, check=True):
    r = subprocess.run(["gh", *a], capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        raise RuntimeError(f"gh {' '.join(a[:2])} 실패: {r.stderr.strip()[-300:]}")
    return r.stdout


def put(nxt):
    print("다음 확인:", nxt)
    if OUT:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(f"next={nxt}\n")


def next_wait(hours, due=None):
    """발행 시간대 안이면 5분 뒤 — 간격이 풀리는 시각(due)이 5분 안이면 그 직후(1~4분)에 깨어난다
    (5분 단위면 간격이 62~67분으로 벌어져 하루 10개를 19시대 안에 못 채우는 날이 생김).
    시간대 밖이면 시작 5분 전까지 크게 건너뛴다(밤엔 몇 번만 돈다)."""
    now = dt.datetime.now()  # TZ=Asia/Seoul
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start, end = day + dt.timedelta(hours=min(hours)), day + dt.timedelta(hours=max(hours) + 1)
    if start <= now < end:
        left = (due.replace(tzinfo=None) - now).total_seconds() / 60 if due else 0
        return f"wait{max(1, math.ceil(left))}" if 0 < left < 5 else "wait5"
    if now >= end:
        start += dt.timedelta(days=1)
    mins = (start - now).total_seconds() / 60 - 5
    for m in (240, 60, 30):
        if mins >= m:
            return f"wait{m}"
    return "wait5"


def fetch(src, dst):
    txt = gh("api", f"repos/{R}/contents/{src}?ref=main", "-H", "Accept: application/vnd.github.raw")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(txt)


def main():
    try:
        for src in ("tc/common.py", "config.json", "data/queue.json"):
            fetch(src, "w/" + src)
    except Exception as e:
        print("대기열 읽기 실패(다음 회차에 다시):", e)
        put("wait5")
        return
    results = []
    for acc, sub in ACCOUNTS:
        root = "w/" + sub if sub else "w"
        if sub:
            try:
                for src in ("config.json", "data/queue.json"):
                    fetch(f"{sub}/{src}", f"{root}/{src}")
            except Exception:
                continue   # 그 계정 칸이 아직 없음
        env = dict(os.environ, TC_ROOT=os.path.abspath(root))
        r = subprocess.run([sys.executable, "-c", CHECK], capture_output=True, text=True, encoding="utf-8", env=env)
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            print(f"[{acc or 'main'}] 판단 실패:", (r.stderr or r.stdout)[-300:])
            continue
        res["acc"] = acc
        results.append(res)
    if not results:
        put("wait5"); return
    hours = sorted({h for r in results for h in r["hours"]})
    now = dt.datetime.now().astimezone()
    dues = [dt.datetime.fromisoformat(r["due"]) for r in results if r.get("due")]
    dues = [d for d in dues if d > now]
    put(next_wait(hours, min(dues) if dues else None))
    st = gh("run", "list", "-R", R, "--workflow", "publish.yml", "--limit", "1",
            "--json", "status", "--jq", ".[0].status", check=False).strip()
    if st in BUSY:
        print("발행 실행 중 → 건너뜀")
        return
    for r in results:
        name = r["acc"] or "main"
        if r["why"]:
            print(f"[{name}]", r["why"], "→ 건너뜀")
            continue
        args = ["workflow", "run", "publish.yml", "-R", R] + (["-f", f"account={r['acc']}"] if r["acc"] else [])
        gh(*args)
        print(f"[{name}] 발행 깨움:", R)
        return   # 한 회차에 하나만(같은 발행 워크플로라 겹치면 대기열에서 밀림) — 다른 계정은 다음 회차(1~5분 뒤)


if __name__ == "__main__":
    main()
