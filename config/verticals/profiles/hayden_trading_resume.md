# Hayden Hamilton

Madison, WI | +1 612-323-8498 | haydenham10@gmail.com | LinkedIn | GitHub

## Education

**University of Wisconsin-Madison** — Expected May 2027
B.S., Double Major in Computer Science & Economics | Madison, WI

- Involvement: Claude Builders Club AI Hackathon, Phi Gamma Delta Executive Board Member
- Relevant Coursework: Data Structures and Algorithms, Machine Learning and AI, Operating Systems, Web Design, Statistics, Calculus, Linear Algebra, Microeconomics, Macroeconomics, Object Oriented Programming

## Professional Experience

**Optum (UnitedHealth Group)** — Technology Development Intern | Remote | June 2026 – Present

- Build and maintain data ETL pipelines in Snowflake, transforming raw source data into clean, queryable models for downstream analytics and reporting.
- Develop SQL transformations and data-quality validation checks to improve pipeline reliability across internal datasets.

**MARA Holdings** — Software Engineering Intern | Remote | June 2025 – December 2025

- Built the SlipStream Revenue Tracker in Rust to scan Bitcoin blocks and calculate SlipStream fee revenue for internal reporting.
- Switched from RPC calls to bitcoin-kernel node access with batched processing and tests for 100x faster, more reliable analysis.
- Implemented Prometheus monitoring to Kaspa pool, achieving 100x faster metrics collection and scaling capacity to 3x more miners.
- Mined and analyzed a year of block data to assess revenue impact of key software, guiding deployment and investment decisions.

**University of Wisconsin-Madison** — Software Developer | Hybrid, Madison, WI | May 2025 – September 2025

- Refactored and optimized a Python research project, improving runtime by ~35%, enabling reliable data processing and visualization.
- Built and deployed a cloud-hosted full-stack web app (Python, JS), making research insights accessible to professors and graduates.
- Refactored a legacy PHP web app, transforming a broken codebase into a production-ready system with improved functionality.
- Enhanced infrastructure by adding containerization, email integration, and database management, supporting production deployment.

## Projects

**Strait of Hormuz Event Study**

- Built an event-study web app (FastAPI + React/Vite/TypeScript) quantifying how 2026 Iran-crisis events moved oil prices vs. physical ship transits through the Strait of Hormuz, one data point per event.
- Architected a layered offline pipeline — raw seed CSVs → pure window-math compute → processed JSON served read-only — separating computation from a thin read-only API.
- Built the centerpiece visualization: a category-colored scatter of price impact vs. transit impact, surfacing that verbal escalations move prices but not ships while kinetic events move both.

**Flight Delay Cascade Simulator**

- Built a full-stack flight-delay cascade simulator (FastAPI + pandas backend, React + Vite frontend) modeling how a single delayed or cancelled flight propagates through an airline's network.
- Implemented two deterministic propagation models over the U.S. DOT BTS on-time-performance dataset: aircraft/tail cascade (delay carried across an aircraft's sequential legs until ground slack absorbs it) and passenger-connection risk (connections dropping below the 45-minute minimum).
- Designed the propagation core as a pure, deterministic function returning every affected downstream flight split by mechanism, with a cancelled flight modeled as an unbounded delay.

## Skills & Interests

**Tech Stack:** Python, Java, C, Rust, JavaScript, TypeScript, React, FastAPI, pandas, SQL, Snowflake, PostgreSQL, Redis, Google Cloud, HTML, CSS, R, Bash, Linux, Git

**Interests:** Quantitative Trading & Market Microstructure, Commodities & Quantitative Analysis, AI and Machine Learning, Water Skiing, Golf
