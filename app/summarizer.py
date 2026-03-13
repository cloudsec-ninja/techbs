"""
LLM summary for TechBS transcript data.
Supported providers: ollama (local, default), claude, openai, gemini
"""
import json
import os
import sys
from pathlib import Path

import requests
from rich.console import Console
from rich.table import Table
from rich import box


DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
}

OLLAMA_BASE = "http://localhost:11434"
CONFIG_PATH = Path.home() / ".techbs" / "llm_config.json"


def load_llm_config() -> dict:
    """Return saved LLM config dict, or {} if not configured."""
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_llm_config(provider: str, model: str) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"provider": provider, "model": model}, indent=2))


class LLMSummarizer:
    def __init__(self, provider: str, model: str | None = None):
        self.provider = provider
        self.model = model or DEFAULT_MODELS.get(provider)
        self.console = Console()

    # ── Ollama model selection ─────────────────────────────────────────────────

    def select_ollama_model(self) -> str:
        """Query Ollama for installed models and prompt the user to pick one."""
        try:
            resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
            resp.raise_for_status()
            models = resp.json().get("models", [])
        except requests.exceptions.ConnectionError:
            self.console.print("[red]Cannot connect to Ollama. Is it running?[/]")
            self.console.print("[dim]Start it with: ollama serve[/]")
            sys.exit(1)
        except Exception as e:
            self.console.print(f"[red]Ollama error: {e}[/]")
            sys.exit(1)

        if not models:
            self.console.print("[red]No Ollama models found.[/]")
            self.console.print("[dim]Pull one with: ollama pull llama3.2[/]")
            sys.exit(1)

        if len(models) == 1:
            name = models[0]["name"]
            self.console.print(f"[dim]Using Ollama model:[/] [bold cyan]{name}[/]")
            return name

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("#", style="bold", width=3)
        table.add_column("Model", style="bold cyan", min_width=24)
        table.add_column("Size", style="dim")

        for i, m in enumerate(models, 1):
            size = m.get("size", 0)
            size_str = f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"
            table.add_row(str(i), m["name"], size_str)

        self.console.print()
        self.console.print("[bold cyan]Available Ollama models:[/]")
        self.console.print(table)

        while True:
            try:
                choice = input(f"Select model [1-{len(models)}]: ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    name = models[idx]["name"]
                    save_llm_config("ollama", name)
                    self.console.print(f"[dim]Preference saved — future runs will use this automatically.[/]")
                    return name
            except (ValueError, EOFError):
                pass
            self.console.print(f"[red]Enter a number between 1 and {len(models)}[/]")

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, data: dict) -> str:
        s = data["summary"]
        lines = [
            "You are reviewing a tech talk scored by TechBS, an automated BS detector.\n",
            "Scoring labels:",
            "  LEGIT:   Technical depth, real actionable content, specific details",
            "  NEUTRAL: Off-topic, introductions, small talk, logistics",
            "  BS:      Marketing hype, buzzwords, vague claims, no technical substance\n",
            "═══ ANALYSIS RESULTS ═══",
            f"File: {data['file']}",
            f"Duration: {s['duration_seconds']:.0f}s  |  Chunks: {s['total_chunks']}",
            f"Overall verdict: {data['overall_verdict']}\n",
            f"LEGIT:   {s['legit_pct']}% ({s['legit_count']} chunks)",
            f"NEUTRAL: {s['neutral_pct']}% ({s['neutral_count']} chunks)",
            f"BS:      {s['bs_pct']}% ({s['bs_count']} chunks)\n",
            "═══ TRANSCRIPT WITH SCORES ═══",
            "Format: Chunk N [start-end] LABEL (L:legit% N:neutral% B:bs%) — text\n",
        ]

        for c in data["chunks"]:
            label = c["label"].upper()
            l_pct = int(c["legit_score"] * 100)
            n_pct = int(c["neutral_score"] * 100)
            b_pct = int(c["bs_score"] * 100)
            snippet = c["transcript"][:200].replace("\n", " ")
            if len(c["transcript"]) > 200:
                snippet += "..."
            lines.append(
                f"Chunk {c['index']} [{c['start']:.0f}s-{c['end']:.0f}s] {label}"
                f" (L:{l_pct}% N:{n_pct}% B:{b_pct}%) — {snippet}"
            )

        lines += [
            "\n═══ YOUR TASK ═══",
            "Is the CyberBS analysis accurate? Give a thorough, evidence-based evaluation.\n",
            "Follow this structure exactly:\n",
            "**Opening verdict** — One definitive sentence stating whether the overall scores are accurate.",
            "  Be direct. Do not hedge.\n",
            "**Numbered bold sections** — 3 to 5 sections, each analysing a distinct pattern in the data.",
            "  Each section must:",
            "    - Have a bold header describing the pattern (e.g. **1. It Correctly Captures the Sales-Pitch Delivery**)",
            "    - Cite specific chunk numbers and their exact scores as evidence",
            "      (e.g. 'Chunk 19: bs_score 0.98', 'Chunk 42: legit_score 0.89')",
            "    - Quote short excerpts from the transcript to support the point",
            "    - Explain WHY the model scored it that way, not just what it scored",
            "    - Call out any nuances or edge cases",
            "      (e.g. a chunk that lists real tools but is still scored BS because it lacks technical depth)\n",
            "**Conclusion** — One sentence on the talk's practical value to a working tech professional.",
        ]

        return "\n".join(lines)

    # ── Public entry point ─────────────────────────────────────────────────────

    def summarize(self, transcript_path: Path) -> None:
        data = json.loads(transcript_path.read_text(encoding="utf-8", errors="replace"))
        prompt = self._build_prompt(data)

        self.console.rule("[bold cyan]LLM Summary[/]")
        self.console.print(
            f"[dim]Provider: {self.provider}  |  Model: {self.model}[/]\n"
        )

        if self.provider == "ollama":
            self._call_ollama(prompt)
        elif self.provider == "claude":
            self._call_claude(prompt)
        elif self.provider == "openai":
            self._call_openai(prompt)
        elif self.provider == "gemini":
            self._call_gemini(prompt)

        self.console.print()

    # ── Provider implementations ───────────────────────────────────────────────

    def _call_ollama(self, prompt: str) -> None:
        try:
            resp = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                },
                stream=True,
                timeout=180,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        print(content, end="", flush=True)
            print()
        except requests.exceptions.ConnectionError:
            self.console.print("[red]Lost connection to Ollama during generation.[/]")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                self.console.print(f"[red]Ollama model '{self.model}' not found.[/]")
                self.console.print("[dim]Check installed models with: ollama list[/]")
                self.console.print(f"[dim]Pull it with: ollama pull {self.model}[/]")
            else:
                self.console.print(f"[red]Ollama error: {e}[/]")
        except Exception as e:
            self.console.print(f"[red]Ollama error: {e}[/]")

    def _call_claude(self, prompt: str) -> None:
        try:
            import anthropic
        except ImportError:
            self.console.print("[red]anthropic package not installed.[/]")
            self.console.print("[dim]pip install anthropic[/]")
            return

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self.console.print("[red]ANTHROPIC_API_KEY environment variable is not set.[/]")
            return

        try:
            client = anthropic.Anthropic(api_key=api_key)
            with client.messages.stream(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
            print()
        except Exception as e:
            self.console.print(f"[red]Claude error: {e}[/]")

    def _call_openai(self, prompt: str) -> None:
        try:
            import openai
        except ImportError:
            self.console.print("[red]openai package not installed.[/]")
            self.console.print("[dim]pip install openai[/]")
            return

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            self.console.print("[red]OPENAI_API_KEY environment variable is not set.[/]")
            return

        try:
            client = openai.OpenAI(api_key=api_key)
            stream = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                stream=True,
            )
            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
            print()
        except Exception as e:
            self.console.print(f"[red]OpenAI error: {e}[/]")

    def _call_gemini(self, prompt: str) -> None:
        try:
            from google import genai
        except ImportError:
            self.console.print("[red]google-genai package not installed.[/]")
            self.console.print("[dim]pip install google-genai[/]")
            return

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self.console.print("[red]GOOGLE_API_KEY environment variable is not set.[/]")
            return

        try:
            client = genai.Client(api_key=api_key)
            for chunk in client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
            ):
                if chunk.text:
                    print(chunk.text, end="", flush=True)
            print()
        except Exception as e:
            self.console.print(f"[red]Gemini error: {e}[/]")
