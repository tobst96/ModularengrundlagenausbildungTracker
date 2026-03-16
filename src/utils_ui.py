import streamlit as st

def apply_custom_design():
    """Apply global premium look and customized CSS injection."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"]  {
            font-family: 'Inter', sans-serif;
        }

        /* --- Design Tokens --- */
        :root {
            --primary-red: #ff4b4b;
            --primary-red-glow: rgba(255, 75, 75, 0.4);
            --glass-bg: rgba(255, 255, 255, 0.03);
            --glass-border: rgba(255, 255, 255, 0.1);
            --shadow-sm: 0 2px 4px rgba(0,0,0,0.1);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.2);
            --radius-md: 12px;
            --radius-lg: 16px;
        }

        /* --- Main Layout --- */
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 3rem !important;
        }

        /* --- Glassmorphism Cards (Metrics, Containers) --- */
        div[data-testid="stMetric"] {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            padding: 1.25rem !important;
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-sm);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-4px);
            background: rgba(255, 255, 255, 0.06);
            border-color: rgba(255, 75, 75, 0.3);
            box-shadow: 0 8px 16px rgba(0,0,0,0.3);
        }

        /* --- Enhanced DataFrames --- */
        div[data-testid="stDataFrame"] {
            background: rgba(0, 0, 0, 0.2);
            border-radius: var(--radius-md) !important;
            border: 1px solid var(--glass-border);
            overflow: hidden;
            box-shadow: var(--shadow-md);
        }

        /* --- Premium Buttons --- */
        button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, #ff4b4b 0%, #d42424 100%) !important;
            border: none !important;
            border-radius: 10px !important;
            padding: 0.5rem 1.5rem !important;
            font-weight: 600 !important;
            color: white !important;
            transition: all 0.25s ease !important;
            box-shadow: 0 4px 10px var(--primary-red-glow) !important;
        }
        button[data-testid="baseButton-primary"]:hover {
            transform: scale(1.02);
            box-shadow: 0 6px 15px var(--primary-red-glow) !important;
            filter: brightness(1.1);
        }

        /* --- Tab Styling --- */
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 8px;
            background-color: transparent;
        }
        div[data-testid="stTabs"] button[data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 8px 16px;
            background-color: rgba(255, 255, 255, 0.02);
            border: 1px solid transparent;
            transition: all 0.2s;
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            background-color: rgba(255, 75, 75, 0.1);
            border-color: rgba(255, 75, 75, 0.3) rgba(255, 75, 75, 0.3) transparent rgba(255, 75, 75, 0.3);
            color: #ff4b4b !important;
        }

        /* --- Animated Status Widget (Firetruck) --- */
        [data-testid="stStatusWidget"]::before {
            content: '🚒';
            font-size: 1.4rem;
            margin-right: 10px;
            display: inline-block;
            animation: drive 3s infinite linear, siren 0.4s infinite alternate;
        }
        [data-testid="stStatusWidget"] svg { display: none !important; }

        @keyframes drive {
            0% { transform: translateX(-5px); }
            50% { transform: translateX(5px); }
            100% { transform: translateX(-5px); }
        }
        @keyframes siren {
            from { filter: drop-shadow(0 0 2px red); }
            to { filter: drop-shadow(0 0 8px red); }
        }

        /* --- Form Containers --- */
        div[data-testid="stForm"] {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--glass-border);
            padding: 2rem;
            border-radius: var(--radius-lg);
        }

    </style>
    """, unsafe_allow_html=True)
