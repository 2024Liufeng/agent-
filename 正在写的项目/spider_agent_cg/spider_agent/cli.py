"""命令行：试采、查看、审核、继续采集。"""
import argparse
import sys

from . import storage, workflow


def main(argv=None):
    parser = argparse.ArgumentParser(description="招采网站试采和人工审核")
    commands = parser.add_subparsers(dest="command", required=True)
    trial = commands.add_parser("trial", help="创建一个试采任务")
    trial.add_argument("--config", required=True)
    trial.add_argument("--limit", type=int, default=3, help="每个栏目最多试采条数，1-10")
    trial.add_argument("--advisor", action="store_true", help="启用可选模型审核建议")
    trial.add_argument("--write-db", action="store_true", help="将有效试采样本写入环境变量指定的数据库")
    show = commands.add_parser("show", help="显示审核报告")
    show.add_argument("run_id")
    review = commands.add_parser("review", help="保存人工审核决定")
    review.add_argument("run_id")
    decision = review.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true")
    decision.add_argument("--reject", action="store_true")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    collect = commands.add_parser("collect", help="审核通过后采集到本地 JSON")
    collect.add_argument("run_id")
    collect.add_argument("--pages", type=int, required=True, help="每个栏目最多采集页数，1-100")
    stage = commands.add_parser("stage-db", help="将已有试采样本写入指定数据库供审核")
    stage.add_argument("run_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "trial":
            run_id, path = workflow.trial(args.config, args.limit, args.advisor)
            print(f"任务：{run_id}\n报告：{path / 'report.md'}\n状态：待人工审核")
            if args.write_db:
                from .database import stage
                target, result = stage(run_id)
                print(f"试采入库：新增 {len(result['inserted'])}，重复 {len(result['duplicates'])}，待处理 {len(result['skipped'])}\n入库报告：{target}")
        elif args.command == "show":
            path = storage.run_path(args.run_id)
            print((path / "report.md").read_text(encoding="utf-8"))
            if (path / "review.json").exists():
                print("审核状态：", storage.read(path / "review.json")["decision"])
        elif args.command == "review":
            result = workflow.review(args.run_id, args.approve, args.reviewer, args.note)
            print("审核状态：", result["decision"])
        elif args.command == "collect":
            path, result = workflow.collect(args.run_id, args.pages)
            print(f"采集状态：{result['status']}\n记录数：{len(result['records'])}\n结果：{path}")
            if result["status"] == "partial":
                return 2
        elif args.command == "stage-db":
            from .database import stage
            target, result = stage(args.run_id)
            print(f"试采入库：新增 {len(result['inserted'])}，重复 {len(result['duplicates'])}，待处理 {len(result['skipped'])}\n入库报告：{target}")
    except (OSError, ValueError, KeyError) as exc:
        print(f"操作失败：{exc}", file=sys.stderr)
        return 1
    return 0
