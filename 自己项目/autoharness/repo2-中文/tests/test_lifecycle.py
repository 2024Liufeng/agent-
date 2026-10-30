from autoharness.lib import lifecycle


def _m(name, calls, anchor=0):
    return {"name": name, "calls": calls, "anchor": anchor}


def test_probation_never_archived():
    # denom = 5 - 0 = 5 < 成熟度 10 → 缓刑，即使呼叫次数为零
    out = lifecycle.evaluate([_m("new", 0)], request_count=5, maturity=10, capacity=1)
    assert out == []


def test_graduation_review_archives_mature_zero_calls_without_capacity_pressure():
    # denom = 20 ≥ 成熟度 10，调用 0 → 审核时存档，从未进入池中
    out = lifecycle.evaluate([_m("idle", 0)], request_count=20, maturity=10, capacity=5)
    assert out == ["idle"]


def test_graduated_low_rate_survives_without_capacity_pressure():
    # 呼叫≥1名毕业生；低利率本身并不是死亡线（产能争夺才是）
    out = lifecycle.evaluate([_m("rare", 1)], request_count=1000, maturity=10, capacity=5)
    assert out == []


def test_review_and_capacity_compose():
    # 闲置经审核存档；然后分级​​池分别争夺容量
    members = [_m("idle", 0), _m("hi", 80), _m("lo", 5)]
    out = lifecycle.evaluate(members, request_count=100, maturity=10, capacity=1)
    assert out == ["idle", "lo"]


def test_capacity_competition_archives_lowest_rate():
    members = [_m("hi", 80), _m("mid", 40), _m("lo", 5)]  # 每个面值 100，汇率 0.8/.4/.05
    out = lifecycle.evaluate(members, request_count=100, maturity=10, capacity=2)
    assert out == ["lo"]  # 只选择成熟池中最弱的，并限制容量


def test_high_rate_kept_under_capacity():
    members = [_m("a", 50), _m("b", 90)]
    out = lifecycle.evaluate(members, request_count=100, maturity=10, capacity=5)
    assert out == []  # 容量不足 → 无人存档


def test_denominator_grows_with_requests():
    # 相同符号：在低请求数下试用，一旦 denom 通过成熟就加入成熟池
    m = [_m("x", 0, anchor=0), _m("y", 8, anchor=0)]
    assert lifecycle.evaluate(m, request_count=9, maturity=10, capacity=1) == []       # denom 9 < 10：均为缓刑
    assert lifecycle.evaluate(m, request_count=10, maturity=10, capacity=1) == ["x"]   # 成熟池 2 超过上限 1，最低利率


def test_anchor_offsets_denominator():
    # 创建较晚（锚点 95）： 面值 = 100 - 95 = 5 < 到期日 → 仍处于试用期
    out = lifecycle.evaluate([_m("late", 0, anchor=95)], request_count=100, maturity=10, capacity=1)
    assert out == []


def test_capacity_tiebreak_by_hash_is_deterministic():
    # 同等费率使用稳定的哈希值，而不是倾向于按字母顺序排列的名字。
    members = [_m("b", 10), _m("a", 10), _m("c", 10)]  # 所有率.1
    for ordered in (members, list(reversed(members))):
        out = lifecycle.evaluate(ordered, request_count=100, maturity=10, capacity=2)
        assert out == ["c"]


def test_probation_does_not_count_toward_capacity():
    # 一名成熟幸存者+两名缓刑；缓刑成员未违反能力 1
    members = [_m("mature", 50, anchor=0), _m("p1", 0, anchor=95), _m("p2", 0, anchor=96)]
    out = lifecycle.evaluate(members, request_count=100, maturity=10, capacity=1)
    assert out == []  # 试用期排除在成熟池之外，无产能压力


# ---三向分子：率只吃用；观点是毕业赦免（第10阶段，方向C）---

def _m3(name, use, view=0, anchor=0):
    return {"name": name, "use": use, "view": view, "anchor": anchor}


def test_graduation_review_needs_use_and_view_both_zero():
    # 已查看但从未调用：内容具有回忆值（读取是测量的主导路径）-> 幸免
    out = lifecycle.evaluate([_m3("viewed", 0, view=3)], request_count=20, maturity=10, capacity=5)
    assert out == []
    out = lifecycle.evaluate([_m3("dead", 0, view=0)], request_count=20, maturity=10, capacity=5)
    assert out == ["dead"]


def test_graduation_review_suspend_gate_archives_nothing(monkeypatch):
    out = lifecycle.evaluate([_m3("dead", 0)], request_count=20, maturity=10, capacity=5,
                             review_suspended=True)
    assert out == []  # 破面期：零使用绝不能等于死刑


def test_view_never_feeds_the_rate():
    # 容量竞赛：高观看率/低使用率不得超过低观看率/高使用率
    members = [_m3("viewy", 1, view=99), _m3("usey", 50, view=0)]
    out = lifecycle.evaluate(members, request_count=100, maturity=10, capacity=1)
    assert out == ["viewy"]
