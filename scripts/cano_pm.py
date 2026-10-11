#!/usr/bin/env python3
"""
Cano Project Manager CLI (cano-pm)
Command-line interface to inspect, query, and update Cano project statuses,
milestones, and parked durations.
"""

import sys
import os
import json
import argparse

# Add operator package to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "operator")))

try:
    from project_manager import (
        load_projects_registry,
        list_projects,
        get_project,
        update_project,
        park_project,
        unpark_project,
        format_projects_table,
        format_markdown_summary,
        resolve_projects_yaml_path,
    )
except ImportError as e:
    # If called from a location where operator isn't directly resolved
    alt_path = "/home/ubuntu/dev/observer/operator"
    if os.path.exists(alt_path) and alt_path not in sys.path:
        sys.path.insert(0, alt_path)
        from project_manager import (
            load_projects_registry,
            list_projects,
            get_project,
            update_project,
            park_project,
            unpark_project,
            format_projects_table,
            format_markdown_summary,
            resolve_projects_yaml_path,
        )
    else:
        raise e


def cmd_list(args):
    projects = list_projects(status_filter=args.status, file_path=args.file)
    if args.json:
        print(json.dumps(projects, indent=2))
    else:
        print(format_projects_table(projects))


def cmd_get(args):
    proj = get_project(args.slug, file_path=args.file)
    if not proj:
        print(f"Error: Project '{args.slug}' not found in registry.", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(proj, indent=2))
        return

    print("=" * 60)
    print(f"📌 {proj.get('name', args.slug)} ({proj.get('slug', args.slug)})")
    print("=" * 60)
    print(f"  Category:        {proj.get('category', 'N/A')}")
    print(f"  Status:          {proj.get('status', 'N/A').upper()}")
    if proj.get('status_reason'):
        print(f"  Status Reason:   {proj.get('status_reason')}")
    if proj.get('parked_until'):
        print(f"  Parked Until:    {proj.get('parked_until')}")
    print(f"  Current Focus:   {proj.get('current_focus', 'N/A')}")
    print(f"  Next Milestone:  {proj.get('next_milestone', 'N/A')}")
    print(f"  Repo Path:       {proj.get('repo_path', 'N/A')}")
    containers = proj.get('containers', [])
    if containers:
        print(f"  Containers:      {', '.join(containers)}")
    notes = proj.get('notes', [])
    if notes:
        print("\n  Notes:")
        for n in notes:
            print(f"   • {n}")
    print("=" * 60)


def cmd_set(args):
    updates = {}
    if args.status:
        updates["status"] = args.status
    if args.focus:
        updates["current_focus"] = args.focus
    if args.milestone:
        updates["next_milestone"] = args.milestone
    if args.reason:
        updates["status_reason"] = args.reason
    if args.parked_until:
        updates["parked_until"] = args.parked_until
    if args.note:
        updates["notes"] = args.note

    if not updates:
        print("Warning: No update flags specified. Specify at least one flag to update.", file=sys.stderr)
        sys.exit(1)

    res = update_project(args.slug, updates, file_path=args.file)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"✅ Successfully updated project '{args.slug}'.")
        print(f"   Status:        {res.get('status')}")
        print(f"   Current Focus: {res.get('current_focus')}")
        if res.get('parked_until'):
            print(f"   Parked Until:  {res.get('parked_until')}")


def cmd_park(args):
    res = park_project(args.slug, days=args.days, reason=args.reason, file_path=args.file)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"⏸️  Project '{args.slug}' parked until {res.get('parked_until')}.")
        print(f"   Reason: {res.get('status_reason')}")


def cmd_unpark(args):
    res = unpark_project(args.slug, reason=args.reason, file_path=args.file)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"🟢 Project '{args.slug}' status set to ACTIVE.")


def cmd_markdown(args):
    data = load_projects_registry(file_path=args.file)
    md = format_markdown_summary(data)
    print(md)


def main():
    parser = argparse.ArgumentParser(
        prog="cano-pm",
        description="Cano Ecosystem Project Status & Lifecycle CLI",
    )
    parser.add_argument("--file", "-f", help="Custom path to projects.yaml file", default=None)
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # Common options parent parser
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    common_parser.add_argument("--file", "-f", help="Custom path to projects.yaml file", default=None)

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list
    p_list = subparsers.add_parser("list", aliases=["ls"], parents=[common_parser], help="List all projects")
    p_list.add_argument("--status", "-s", help="Filter by status (e.g. active, parked, maintenance)")
    p_list.set_defaults(func=cmd_list)

    # get
    p_get = subparsers.add_parser("get", aliases=["show"], parents=[common_parser], help="Get details for a specific project")
    p_get.add_argument("slug", help="Project slug or alias (e.g. horizon, volc, observer)")
    p_get.set_defaults(func=cmd_get)

    # set
    p_set = subparsers.add_parser("set", parents=[common_parser], help="Update fields on a project")
    p_set.add_argument("slug", help="Project slug to update")
    p_set.add_argument("--status", "-s", help="New status (active, parked, maintenance, archived)")
    p_set.add_argument("--focus", help="Update current focus description")
    p_set.add_argument("--milestone", help="Update next milestone description")
    p_set.add_argument("--reason", help="Update status reason")
    p_set.add_argument("--parked-until", help="Date until project is parked (YYYY-MM-DD)")
    p_set.add_argument("--note", help="Add a note to project entry")
    p_set.set_defaults(func=cmd_set)

    # park
    p_park = subparsers.add_parser("park", parents=[common_parser], help="Park a project for N days")
    p_park.add_argument("slug", help="Project slug to park")
    p_park.add_argument("--days", "-d", type=int, default=7, help="Number of days to park (default: 7)")
    p_park.add_argument("--reason", "-r", help="Reason for parking")
    p_park.set_defaults(func=cmd_park)

    # unpark
    p_unpark = subparsers.add_parser("unpark", parents=[common_parser], help="Resume/activate a parked project")
    p_unpark.add_argument("slug", help="Project slug to activate")
    p_unpark.add_argument("--reason", "-r", help="Reason for resuming")
    p_unpark.set_defaults(func=cmd_unpark)

    # markdown
    p_md = subparsers.add_parser("markdown", aliases=["md"], parents=[common_parser], help="Print markdown summary report")
    p_md.set_defaults(func=cmd_markdown)

    args = parser.parse_args()
    if not args.command:
        # Default action: list
        args.status = None
        cmd_list(args)
        return

    args.func(args)


if __name__ == "__main__":
    main()
