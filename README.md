# 🔬 Multi-Agent AI Research System

A collaborative AI research platform that leverages multiple specialized AI agents to conduct comprehensive research, analyze information, generate reports, and provide fact-based insights. Each agent is assigned a dedicated role, enabling efficient task delegation and higher-quality research outcomes through agent collaboration. Multi-agent systems are increasingly used to solve complex tasks by combining the strengths of multiple specialized AI agents.

## 🚀 Overview

The system simulates a research team composed of intelligent AI agents working together to transform a user query into a structured research report.

### 🤖 Agent Roles

* 🔍 **Search Agent** – Finds relevant information from the web
* 📖 **Reader Agent** – Extracts and analyzes key information
* ✍️ **Writer Agent** – Creates structured research reports
* 🧐 **Critic Agent** – Reviews content for accuracy and completeness

This collaborative workflow improves research quality by dividing tasks among specialized agents.

## ✨ Features

* 🤖 Multi-Agent Architecture
* 🌐 Automated Web Research
* 📚 Information Extraction & Summarization
* 📝 AI-Generated Research Reports
* 🔍 Fact Verification Workflow
* ⚡ Real-Time Research Processing
* 🎯 Structured Research Output
* 📱 User-Friendly Interface
* 🔄 Agent Collaboration & Feedback Loop

## 🛠️ Tech Stack

### AI Frameworks

* LangChain
* Multi-Agent Workflow Architecture

### AI Models

* Mistral AI / Gemini AI
* Large Language Models (LLMs)

### Research Tools

* Tavily Search API
* BeautifulSoup

### Frontend

* Streamlit

### Backend

* Python

## 📂 Project Structure

```bash
multi-agent-Ai-research-system/
│
├── agents/
│   ├── search_agent.py
│   ├── reader_agent.py
│   ├── writer_agent.py
│   └── critic_agent.py
│
├── tools/
├── workflows/
├── app.py
├── requirements.txt
└── README.md
```

## ⚙️ Installation

### Clone Repository

```bash
git clone https://github.com/Kundank8789/multi-agent-Ai-research-system.git
```

### Navigate to Project

```bash
cd multi-agent-Ai-research-system
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment Variables

Create a `.env` file:

```env
MISTRAL_API_KEY=your_api_key
TAVILY_API_KEY=your_api_key
```

## ▶️ Running the Application

```bash
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## 🎯 How It Works

1. User submits a research topic.
2. Search Agent gathers information from multiple sources.
3. Reader Agent extracts key findings.
4. Writer Agent generates a structured report.
5. Critic Agent reviews and improves the output.
6. Final research report is presented to the user.

## 📸 Screenshots

### Research Interface

```md
![Research Interface](./screenshots/home.png)
```

### Agent Workflow

```md
![Agent Workflow](./screenshots/workflow.png)
```

### Generated Report

```md
![Research Report](./screenshots/report.png)
```

## 🌟 Future Enhancements

* Research citations and source tracking
* PDF report export
* Multi-language research support
* Academic paper integration
* Memory-enabled agents
* Human-in-the-loop review
* Autonomous deep research workflows

## 📈 Key Learning Outcomes

* Multi-Agent System Design
* Agent Collaboration Patterns
* LangChain Workflows
* LLM Orchestration
* Automated Research Pipelines
* AI-Powered Information Retrieval

## 🤝 Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to GitHub
5. Open a Pull Request

## 👨‍💻 Author

**Kundan Kumar**

GitHub: https://github.com/Kundank8789

---

⭐ If you found this project useful, please give it a star on GitHub.
