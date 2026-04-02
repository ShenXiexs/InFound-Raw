from __future__ import annotations

import argparse
from pathlib import Path

from .outreach_filter_snapshot_export import export_creator_filter_items_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export creator_filter_items JSON from an outreach filter raw snapshot.",
    )
    parser.add_argument("--input", required=True, help="Raw outreach snapshot JSON path")
    parser.add_argument("--output", help="Optional output JSON path")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    final_output_path = export_creator_filter_items_snapshot(
        snapshot_path=input_path,
        output_path=output_path,
    )
    print(final_output_path)


if __name__ == "__main__":
    main()
