from __future__ import annotations

"""One-shot compatibility fix after V2 management integration.

Legacy 1.x strategy protection semantics force-flatten before evaluating an
intrabar stop/target once the EOD cutoff has arrived. V2 deliberately keeps its
validated ordering: stop/target, then 60-minute max hold, then EOD force-flat.
This transform changes only that version split and aborts if the reviewed anchor
has moved.
"""

from pathlib import Path


PATH = Path("src/app/trading/strategy_monitor.py")
OLD = '''            trigger_kind = paper_protection_trigger(\n                is_long=True,\n                stop_price=protection.stop_price,\n                target_price=protection.target_price,\n                observation=_paper_observation(execution),\n                activated_at=activated_at,\n            )\n            if trigger_kind == "stop":\n                trigger = "protective_stop"\n            elif trigger_kind == "target":\n                trigger = "profit_target"\n            elif (\n                config.config.strategy_version == "2.0.0"\n                and activated_at is not None\n                and v2_hold_expired(\n                    config.config,\n                    activated_at=activated_at,\n                    observed_at=execution.source_time,\n                )\n            ):\n                trigger = "max_hold"\n            elif force_flat:\n                trigger = "force_flat"\n'''
NEW = '''            if config.config.strategy_version != "2.0.0" and force_flat:\n                # Preserve the original 1.x contract exactly: once force-flat\n                # time is reached, EOD liquidation wins over stop/target checks.\n                trigger = "force_flat"\n            else:\n                trigger_kind = paper_protection_trigger(\n                    is_long=True,\n                    stop_price=protection.stop_price,\n                    target_price=protection.target_price,\n                    observation=_paper_observation(execution),\n                    activated_at=activated_at,\n                )\n                if trigger_kind == "stop":\n                    trigger = "protective_stop"\n                elif trigger_kind == "target":\n                    trigger = "profit_target"\n                elif (\n                    config.config.strategy_version == "2.0.0"\n                    and activated_at is not None\n                    and v2_hold_expired(\n                        config.config,\n                        activated_at=activated_at,\n                        observed_at=execution.source_time,\n                    )\n                ):\n                    trigger = "max_hold"\n                elif force_flat:\n                    trigger = "force_flat"\n'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count != 1:
        raise RuntimeError(f"expected exactly one force-flat precedence anchor, found {count}")
    PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("Restored legacy 1.x force-flat precedence; retained V2 ordering.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
