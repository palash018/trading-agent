import asyncio
import httpx
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich import box

API = "http://localhost:8000"
console = Console()

async def fetch(client, path):
    try:
        r = await client.get(f"{API}{path}", timeout=3)
        return r.json()
    except Exception:
        return None

def stats_panel(stats: dict) -> Panel:
    if not stats:
        return Panel("No data", title="System Stats")
    t = Table(box=None, show_header=False, padding=(0,1))
    t.add_column(style="dim")
    t.add_column(style="bold white")
    t.add_row("Ticks ingested", str(stats["ticks"]))
    t.add_row("Sentiment scores", str(stats["sentiment_scores"]))
    t.add_row("LLM calls", f"[yellow]{stats['llm_calls']}[/]")
    t.add_row("Rule-based", f"[green]{stats['rule_calls']}[/]")
    saved = round(stats["rule_calls"] / max(stats["sentiment_scores"], 1) * 100)
    t.add_row("LLM cost saved", f"[green]{saved}%[/]")
    t.add_row("Approved trades", f"[green]{stats['approved_trades']}[/]")
    t.add_row("Rejected trades", f"[red]{stats['rejected_trades']}[/]")
    return Panel(t, title="[bold cyan]System Stats[/]", border_style="cyan", box=box.ROUNDED)

def ticks_panel(btc: list, eth: list) -> Panel:
    if not btc and not eth:
        return Panel("No data", title="Market Data")
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
    t.add_column("Symbol")
    t.add_column("Price", justify="right")
    t.add_column("Volume", justify="right")
    t.add_column("Change", justify="right")

    for symbol, rows in [("BTCUSDT", btc), ("ETHUSDT", eth)]:
        if not rows or len(rows) < 2:
            continue
        latest = rows[-1]
        prev = rows[-2]
        change = ((latest["close"] - prev["close"]) / prev["close"]) * 100
        color = "green" if change >= 0 else "red"
        arrow = "▲" if change >= 0 else "▼"
        t.add_row(
            f"[bold]{symbol}[/]",
            f"[{color}]${latest['close']:,.2f}[/]",
            f"{latest['volume']:.4f}",
            f"[{color}]{arrow} {abs(change):.3f}%[/]",
        )
    return Panel(t, title="[bold magenta]Live Market Data[/]", border_style="magenta", box=box.ROUNDED)

def sentiment_panel(btc_s: list, eth_s: list) -> Panel:
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold yellow")
    t.add_column("Symbol")
    t.add_column("Score", justify="right")
    t.add_column("Via")
    t.add_column("Headline")

    for symbol, rows in [("BTC", btc_s), ("ETH", eth_s)]:
        if not rows:
            continue
        r = rows[0]
        score = r["score"]
        color = "green" if score > 0.2 else "red" if score < -0.2 else "yellow"
        via = "[yellow]LLM[/]" if r["llm_used"] else "[green]RULE[/]"
        headline = (r["headline"] or "")[:45] + "..."
        t.add_row(
            f"[bold]{symbol}[/]",
            f"[{color}]{score:+.2f}[/]",
            via,
            f"[dim]{headline}[/]",
        )
    return Panel(t, title="[bold yellow]Sentiment[/]", border_style="yellow", box=box.ROUNDED)

def proposals_panel(proposals: list) -> Panel:
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold blue")
    t.add_column("Symbol")
    t.add_column("Dir")
    t.add_column("Conf", justify="right")
    t.add_column("Status")
    t.add_column("Reasoning")

    for p in proposals[:6]:
        status = p["status"]
        status_str = {
            "APPROVED": "[green]✅ APPROVED[/]",
            "REJECTED": "[red]❌ REJECTED[/]",
            "PENDING":  "[yellow]⏳ PENDING[/]",
        }.get(status, status)
        dir_color = "green" if p["direction"] == "BUY" else "red" if p["direction"] == "SELL" else "dim"
        t.add_row(
            f"[bold]{p['symbol']}[/]",
            f"[{dir_color}]{p['direction']}[/]",
            f"{p['confidence']:.2f}",
            status_str,
            f"[dim]{(p['reasoning'] or '')[:50]}...[/]",
        )
    return Panel(t, title="[bold blue]Trade Proposals[/]", border_style="blue", box=box.ROUNDED)

def risk_panel(risk: list) -> Panel:
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold red")
    t.add_column("Decision")
    t.add_column("Reason")

    for r in risk[:5]:
        color = "green" if r["decision"] == "APPROVED" else "red"
        icon = "✅" if r["decision"] == "APPROVED" else "❌"
        t.add_row(
            f"[{color}]{icon} {r['decision']}[/]",
            f"[dim]{(r['reason'] or '')[:60]}[/]",
        )
    return Panel(t, title="[bold red]Risk Audit Log[/]", border_style="red", box=box.ROUNDED)

def make_layout(stats, btc, eth, btc_s, eth_s, proposals, risk) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="top", size=10),
        Layout(name="middle", size=12),
        Layout(name="bottom", size=10),
    )
    layout["top"].split_row(
        Layout(stats_panel(stats), name="stats"),
        Layout(ticks_panel(btc, eth), name="ticks"),
    )
    layout["middle"].split_row(
        Layout(sentiment_panel(btc_s, eth_s), name="sentiment"),
        Layout(proposals_panel(proposals), name="proposals"),
    )
    layout["bottom"].ratio = 1
    layout["bottom"].update(risk_panel(risk))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    layout["header"].update(
        Panel(
            Text(f"🤖 Trading Agent Observability Dashboard  •  {now}  •  press Ctrl+C to exit",
                 justify="center", style="bold white"),
            border_style="bright_black"
        )
    )
    return layout

async def run():
    async with httpx.AsyncClient() as client:
        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                stats, btc, eth, btc_s, eth_s, proposals, risk = await asyncio.gather(
                    fetch(client, "/stats"),
                    fetch(client, "/ticks/BTCUSDT?limit=30"),
                    fetch(client, "/ticks/ETHUSDT?limit=30"),
                    fetch(client, "/sentiment/BTC"),
                    fetch(client, "/sentiment/ETH"),
                    fetch(client, "/proposals"),
                    fetch(client, "/risk"),
                )
                live.update(make_layout(stats, btc, eth, btc_s, eth_s, proposals, risk))
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run())
