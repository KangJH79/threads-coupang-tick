"""PC 없이 1시간 1개 발행 — 비공개 저장소(threads-coupang)의 대기열을 보고 발행할 차례면 publish.yml 을 깨운다.
tick.yml 이 5분마다(회차가 끝날 때 다음 회차를 직접 부르는 사슬) 실행한다.
간격(60분+1분)·시간대·한 시간 1개·API 막힘 판단은 비공개 저장소의 tc/common.py publish_due 를 그대로 받아 쓴다.
다음 회차까지 기다릴 환경(wait5/wait30/wait60/wait240)을 GITHUB_OUTPUT 의 next 로 넘긴다."""
import os, sys, json, subprocess, datetime as dt

R = os.environ.get("R", "KangJH79/threads-coupang")
OUT = os.environ.get("GITHUB_OUTPUT")
BUSY = ("queued", "in_progress", "waiting", "pending", "requested")


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


def next_wait(hours):
    """발행 시간대 안이면 5분 뒤, 밖이면 시간대 시작 5분 전까지 크게 건너뛴다(밤엔 몇 번만 돈다)."""
    now = dt.datetime.now()  # TZ=Asia/Seoul
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start, end = day + dt.timedelta(hours=min(hours)), day + dt.timedelta(hours=max(hours) + 1)
    if start <= now < end:
        return "wait5"
    if now >= end:
        start += dt.timedelta(days=1)
    mins = (start - now).total_seconds() / 60 - 5
    for m in (240, 60, 30):
        if mins >= m:
            return f"wait{m}"
    return "wait5"


def main():
    os.makedirs("w/tc", exist_ok=True)
    os.makedirs("w/data", exist_ok=True)
    try:
        for src, dst in (("tc/common.py", "w/tc/common.py"), ("config.json", "w/config.json"),
                         ("data/queue.json", "w/data/queue.json")):
            txt = gh("api", f"repos/{R}/contents/{src}?ref=main", "-H", "Accept: application/vnd.github.raw")
            with open(dst, "w", encoding="utf-8") as f:
                f.write(txt)
    except Exception as e:
        print("대기열 읽기 실패(다음 회차에 다시):", e)
        put("wait5")
        return
    sys.path.insert(0, os.path.abspath("w/tc"))
    import common
    put(next_wait(common.config().get("publish_hours") or list(range(10, 20))))
    st = gh("run", "list", "-R", R, "--workflow", "publish.yml", "--limit", "1",
            "--json", "status", "--jq", ".[0].status", check=False).strip()
    if st in BUSY:
        print("발행 실행 중 → 건너뜀")
        return
    q = json.load(open(common.QUEUE, encoding="utf-8"))
    why = common.publish_due(q)
    if why:
        print(why, "→ 건너뜀")
        return
    gh("workflow", "run", "publish.yml", "-R", R)
    print("발행 깨움:", R)


if __name__ == "__main__":
    main()
