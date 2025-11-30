# ARCANE

This repository contains the official replication package and source code for the research paper: **"Autonomic Framework for Vulnerability Repair and Technical Debt Reduction using Language Models."**

ARCANE is an experimental software agent designed to autonomously fix logical bugs in Java programs. It uses a Monitor-Analyze-Plan-Execute (MAPE-K) loop to iteratively generate patches, validate them against test suites, and analyze architectural metrics using SonarCloud.

## Experiment Overview

This project evaluates three distinct agent architectures against the QuixBugs benchmark (Java):

* **BaselineNaive:** A standard, single-shot LLM repair agent.
* **BaselineAware:** An agent using Chain-of-Thought (CoT) prompting but running open-loop.
* **ArcaneAgent:** An autonomic agent with a self-healing retry loop, capable of analyzing validator error messages and architectural metrics to refine its patches.

## Getting Started

### Prerequisites

* Python 3.10+
* Java JDK 21 (Required for compiling the benchmark)
* Gradle (Required for building the benchmark)
* SonarScanner CLI (Required for metric analysis)

### Installation

Clone the repository:

```bash
git clone [https://github.com/YOUR_USERNAME/ARCANE.git](https://github.com/YOUR_USERNAME/ARCANE.git)
cd ARCANE 
