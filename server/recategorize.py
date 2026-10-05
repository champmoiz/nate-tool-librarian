"""
recategorize.py — one-shot cleanup of tools.txt for better RAG recall.
Backs up tools.txt -> tools.txt.bak, remaps categories to 19 canonical
buckets, adds alias strings (7th field) to high-value tools, comments
out research-failed rows.
"""
from pathlib import Path
import shutil, sys

TOOLS = Path(r"D:\Nate\tools\tools.txt")
BAK   = Path(r"D:\Nate\tools\tools.txt.bak")

CATEGORY_MAP = {
    "AI Agent Frameworks": "AI Agents & Frameworks",
    "AI Agent Workspaces": "AI Agents & Frameworks",
    "AI Agent Tools": "AI Agents & Frameworks",
    "Local AI Assistants": "AI Agents & Frameworks",
    "AI Agent Memory": "AI Agents & Frameworks",
    "AI Memory": "AI Agents & Frameworks",
    "AI Agent Skills": "AI Agent Skills",
    "AI Agent Skills (Security)": "AI Agent Skills",
    "Deployment Skills": "AI Agent Skills",
    "AI Model Platform": "AI Models & Inference",
    "AI Models / Platforms": "AI Models & Inference",
    "AI Models": "AI Models & Inference",
    "LLM Inference": "AI Models & Inference",
    "LLM Proxies / Routers": "AI Models & Inference",
    "AI Coding Tools": "AI Coding & App Builders",
    "AI App Builders": "AI Coding & App Builders",
    "Development Environments": "AI Coding & App Builders",
    "Video Generation": "AI Media Generation",
    "Avatar Generation": "AI Media Generation",
    "Digital Humans / Video": "AI Media Generation",
    "Voice / TTS": "AI Media Generation",
    "Text-to-Speech": "AI Media Generation",
    "Automation Platforms": "Automation & Workflows",
    "Chatbot Platforms": "Automation & Workflows",
    "OSINT / Threat Intel": "OSINT & Investigations",
    "OSINT Certificate Search": "OSINT & Investigations",
    "OSINT DNS": "OSINT & Investigations",
    "OSINT Username Tools": "OSINT & Investigations",
    "OSINT Email/Phone": "OSINT & Investigations",
    "OSINT / Link Analysis": "OSINT & Investigations",
    "OSINT / Search": "OSINT & Investigations",
    "OSINT Automation": "OSINT & Investigations",
    "OSINT / Vulnerability Search": "OSINT & Investigations",
    "Face Search / OSINT": "OSINT & Investigations",
    "Geospatial Intelligence": "OSINT & Investigations",
    "Cybersecurity": "Cybersecurity & Pentesting",
    "Security Analysis": "Cybersecurity & Pentesting",
    "Security / Exploitation": "Cybersecurity & Pentesting",
    "Security Monitoring": "Cybersecurity & Pentesting",
    "Security Incident Response": "Cybersecurity & Pentesting",
    "Threat Intelligence": "Cybersecurity & Pentesting",
    "Mobile Forensics": "Mobile Forensics & Devices",
    "Mobile Forensics / Verification": "Mobile Forensics & Devices",
    "Mobile Device Tools": "Mobile Forensics & Devices",
    "Web Crawling / Scraping": "Web Scraping & Crawling",
    "Web Crawling / Recon": "Web Scraping & Crawling",
    "Web Scraping": "Web Scraping & Crawling",
    "AI Web Scraping": "Web Scraping & Crawling",
    "Browser Automation": "Browser Automation",
    "Agentic Web Automation": "Browser Automation",
    "Browser Tooling": "Browser Automation",
    "Backend-as-a-Service": "Backend & Infrastructure",
    "Databases": "Backend & Infrastructure",
    "AI Infrastructure / Sandboxes": "Backend & Infrastructure",
    "Cloud Platforms": "Backend & Infrastructure",
    "Secrets Management": "Backend & Infrastructure",
    "Developer Tools": "Developer Tools",
    "Development Tools": "Developer Tools",
    "CLI Tools": "Developer Tools",
    "API Clients": "Developer Tools",
    "API Directories": "Developer Tools",
    "API Marketplaces": "Developer Tools",
    "Web Technology Detection": "Developer Tools",
    "Code Visualization": "Developer Tools",
    "Code Knowledge Graphs": "Developer Tools",
    "Data Engineering": "Developer Tools",
    "Web Frameworks": "Developer Tools",
    "Status Pages": "Developer Tools",
    "UI Component Libraries": "UI Components & Design",
    "UI Animation": "UI Components & Design",
    "UI Animation Libraries": "UI Components & Design",
    "UI Effects": "UI Components & Design",
    "UI Loaders": "UI Components & Design",
    "UI Loaders / Animation": "UI Components & Design",
    "Web Development Tools": "UI Components & Design",
    "Design Resources": "UI Components & Design",
    "Design Tools": "UI Components & Design",
    "Design / Prototyping": "UI Components & Design",
    "Whiteboarding / Diagramming": "UI Components & Design",
    "Diagramming": "UI Components & Design",
    "Image Editors": "UI Components & Design",
    "Motion Design": "UI Components & Design",
    "Video Automation": "Video & Media Production",
    "Video Editing": "Video & Media Production",
    "Video / Shorts Tools": "Video & Media Production",
    "Content Creation": "Video & Media Production",
    "Video Programming": "Video & Media Production",
    "Downloads / Media": "Video & Media Production",
    "Knowledge Management": "Knowledge & Productivity",
    "AI Research Notebooks": "Knowledge & Productivity",
    "Presentation Tools": "Knowledge & Productivity",
    "Document Signing": "Knowledge & Productivity",
    "Document Conversion": "Knowledge & Productivity",
    "Clipboard Tools": "Knowledge & Productivity",
    "Backup Tools": "Knowledge & Productivity",
    "Offline Tools": "Knowledge & Productivity",
    "Utilities": "Knowledge & Productivity",
    "Learning Resources": "Learning & Curated Lists",
    "Learning Platforms": "Learning & Curated Lists",
    "Curated Lists": "Learning & Curated Lists",
    "Password Managers": "Privacy & Security Tools",
    "Privacy Browsers": "Privacy & Security Tools",
    "Secure Operating Systems": "Privacy & Security Tools",
    "Mobile Security OS": "Privacy & Security Tools",
    "Firewalls / Networking": "Privacy & Security Tools",
    "Network Visualization": "Privacy & Security Tools",
    "Operating Systems": "Privacy & Security Tools",
    "CRM": "Business & Operations",
    "Monetization / Payments": "Business & Operations",
    "Customer Support": "Business & Operations",
    "Privacy / Compliance": "Business & Operations",
}

ALIASES = {
    "pipecat":        "voice agent, voice assistant, realtime conversational ai, jarvis, speech pipeline",
    "open-voice":     "voice clone, tts, voice synthesis, jarvis voice",
    "supertonic":     "tts, text to speech, on-device voice, fast voice, jarvis voice",
    "tinytts":        "tts, lightweight voice, on-device voice, jarvis",
    "omnivoice":      "multi voice tts, voice synthesis, jarvis voice",
    "kikivoice":      "voice synthesis, tts",
    "openwhispr":     "speech to text, stt, whisper, voice input, jarvis ears",
    "goose":          "ai agent, autonomous agent, jarvis brain, claude, mcp",
    "openmanus":      "general agent, autonomous agent, jarvis brain",
    "nanobot":        "personal ai agent, self hosted agent, jarvis brain",
    "openmanusbot":   "personal agent, chat agents, jarvis",
    "automaton":      "self improving agent, autonomous agent, jarvis",
    "supermemory":    "agent memory, persistent memory, long term memory, jarvis memory",
    "claude-mem":     "agent memory, session memory, jarvis memory",
    "acontext-memory-layer": "agent memory, context layer, jarvis memory",
    "browseruse":     "browser agent, autonomous browsing, playwright agent, jarvis hands",
    "obscura":        "headless browser, browser agent, jarvis hands",
    "pinchtab":       "browser automation, chrome control, jarvis hands",
    "playwright":     "browser automation, e2e testing, jarvis hands",
    "projectnomad":   "offline wikipedia, offline ai, offline knowledge, jarvis offline mode",
    "obsidian":       "notes, knowledge base, second brain",
    "tolaria":        "markdown knowledge base, second brain",
    "litellm":        "llm proxy, llm router, multi provider, api gateway",
    "omniroute":      "llm gateway, multi provider, api router",
    "unorouter":      "llm gateway, multi provider, api router",
    "9-router":       "llm router, claude code proxy, codex proxy, api gateway",
    "freellmpi":      "free llm api, llm router, multi provider",
    "open-free-llm-api": "free llm apis, llm directory",
    "opencode":       "coding agent, ai coding, terminal agent",
    "kilo-cli":       "coding agent, ai coding cli",
    "claudecodelocal":"local claude code, ollama coding agent",
    "remotion":       "programmatic video, react video, code to video",
    "skyreelsv2":     "ai video generation, text to video",
    "ltx-2-5":        "ai video generation, text to video",
    "autoclips":      "auto clip, shorts generator, video automation",
    "openshorts":     "shorts generator, video automation",
    "spiderfoot":     "osint automation, recon framework, footprinting",
    "shodan":         "iot search engine, device search, internet scanner, banner grab",
    "maltego":        "link analysis, osint graph, relationship mapping",
    "openosint":      "osint framework, email recon, domain recon",
}

JUNK = {"agenticos","anydog","decibel-cli","githubdesigns",
        "never-stop-coding","rolling","sqeezemotion"}

def main():
    if not TOOLS.exists():
        print(f"[ERROR] {TOOLS} not found"); sys.exit(1)
    shutil.copy2(TOOLS, BAK)
    print(f"[OK] Backup: {BAK}")
    out_lines, junk_block = [], []
    stats = {"recat":0,"alias":0,"junk":0,"kept":0,"warn":0}
    for raw in TOOLS.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip(); stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out_lines.append(line); continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) not in (6,7):
            out_lines.append(line); stats["warn"] += 1; continue
        if len(parts) == 7:
            name,cat,ttype,pricing,status,desc,aliases = parts
        else:
            name,cat,ttype,pricing,status,desc = parts; aliases = ""
        key = name.lower().strip()
        if key in JUNK:
            junk_block.append(f"# {name} | {cat} | {ttype} | {pricing} | {status} | {desc}")
            stats["junk"] += 1; continue
        new_cat = CATEGORY_MAP.get(cat, cat)
        if new_cat != cat: stats["recat"] += 1
        if not aliases: aliases = ALIASES.get(key, "")
        if aliases:
            stats["alias"] += 1
            out_lines.append(f"{name} | {new_cat} | {ttype} | {pricing} | {status} | {desc} | {aliases}")
        else:
            out_lines.append(f"{name} | {new_cat} | {ttype} | {pricing} | {status} | {desc}")
        stats["kept"] += 1
    if junk_block:
        out_lines += ["", "# === RESEARCH-FAILED / DO NOT EMBED ==="] + junk_block
    TOOLS.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"[OK] Rewrote {TOOLS}")
    print(f"     kept={stats['kept']} recategorized={stats['recat']} "
          f"with_aliases={stats['alias']} junked={stats['junk']} warnings={stats['warn']}")

if __name__ == "__main__":
    main()
