# Oncology Watch: AI-Driven Healthcare Dashboard

![ML](https://img.shields.io/badge/Machine%20Learning-grey) ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) ![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat&logo=streamlit&logoColor=white)

Welcome to Oncology Watch, a smart remote patient monitoring prototype! 

In the world of outpatient healthcare, catching rapid physiological deterioration (like sepsis) between hospital visits is a necessity. However, relying solely on wearable alarms creates massive "alert fatigue" for nurses, while relying on patient self-reporting means interventions happen too late.

*Then, how do we monitor them safely?*

We need a system that balances both. This project solves that dilemma by combining an unsupervised Machine Learning model (which silently learns the patient's normal baseline) with a subjective daily check-in system. It acts as a smart filter, ensuring nurses only see alarms that truly matter.

---

## Software Overview

The software suite is divided into four main layers:

1. **Layer 1: The AI Engine (`demo/detector.py`)**
   * Uses an Isolation Forest algorithm to establish highly personalized, 4-hour baselines for patient heart rate and activity. 
2. **Layer 2: The Rules Engine (`demo/rules.py`)**
   * The clinical gatekeeper. It calculates a NEWS2-inspired score combining the AI's objective anomaly detection with the patient's subjective check-in data.
3. **Layer 3: State & Data Management (`demo/domain.py`, `demo/services.py`)**
   * Handles the in-memory database (`AppState`), managing all synthetic records, check-in tracking, and nurse audit histories.
4. **Layer 4: The Frontend (`demo/views/`)**
   * A dual-interface Streamlit application featuring a mobile-friendly Patient app and a comprehensive, traffic-light-coded Nurse Dashboard.

---

## Project Architecture

```text
.
├── demo/
│   ├── fixtures/         # Pre-generated synthetic patient data (.csv/.json)
│   ├── tests/            # Pytest suite for rules and services
│   ├── views/            
│   │   ├── charts.py     # Plotly UI logic for historical comparisons
│   │   ├── nurse.py      # Nurse Dashboard UI
│   │   └── patient.py    # Patient Check-in UI
│   ├── app.py            # Main Streamlit application entry point
│   ├── detector.py       # Isolation Forest AI model
│   ├── domain.py         # Data classes and AppState definition
│   ├── rules.py          # NEWS2 scoring and data quality thresholds
│   ├── services.py       # Backend functions for routing data
│   └── simulation.py     # Controls the passage of time for the demo
└── requirements.txt      # Python dependencies
```

---

## Getting Started

To run this project, you will need Python installed. It is highly recommended to use a Virtual Environment so you don't clutter your global system.

### 1. Setup the Virtual Environment
Open your terminal in the root directory of this project and run:

**Mac / Linux:**
```bash
cd demo/
python3 -m venv .venv
source .venv/bin/activate
```

**Windows:**
```cmd
cd demo\
python -m venv .venv
.venv\Scripts\activate
```

### 2. Install Dependencies
With your virtual environment active, install the required packages:
```bash
pip install -r requirements.txt
```

---

## How to Use the Suite

This project is built to be a live presentation prototype. You can run the app or test the logic independently.

### Launching the Dashboard
To start the dual-view Streamlit application:
```bash
streamlit run app.py
```
*(This will open the app in your browser at `http://localhost:8501`)*

### Running the Test Suite
The core clinical logic is quality-controlled by unit tests to ensure safety thresholds (like the SOS trigger) never fail.
```bash
python -m pytest tests/ -q
```

---

## The Demo Integration

To present the 28-day narrative effectively using the UI:
1. Open the app and toggle between **Patient** and **Nurse dashboard** using the sidebar.
2. In the Nurse view, select different patients to see how the system handles stable background data without false alarms.
3. Click the **"Advance 1 Day"** or **"Run to next event"** buttons in the sidebar to simulate the passage of time.
4. Watch for the automated Toast notifications! They will guide you through the story, automatically focusing the UI on the Day 14 deterioration event to demonstrate the AI and Rules Engine in action.
