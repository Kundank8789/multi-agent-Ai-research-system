# ui.py
import streamlit as st
import asyncio
from typing import Dict, Optional
import time
from datetime import datetime
from agents import build_reader_agent, build_search_agent, writer_chain, critic_chain
import json
import re
import os
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from httpx import HTTPStatusError
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Research Pipeline UI",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .step-container {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 5px solid #1f77b4;
    }
    .step-header {
        font-weight: bold;
        color: #1f77b4;
        font-size: 1.2rem;
    }
    .result-box {
        background-color: white;
        border-radius: 5px;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #ddd;
        max-height: 400px;
        overflow-y: auto;
    }
    .metric-card {
        background-color: white;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
    }
    .status-pending {
        background-color: #fff3cd;
        color: #856404;
    }
    .status-running {
        background-color: #cce5ff;
        color: #004085;
    }
    .status-complete {
        background-color: #d4edda;
        color: #155724;
    }
    .status-error {
        background-color: #f8d7da;
        color: #721c24;
    }
    .download-btn {
        margin-top: 1rem;
    }
    .rate-limit-warning {
        background-color: #fff3cd;
        border: 1px solid #ffc107;
        border-radius: 5px;
        padding: 10px;
        margin: 10px 0;
    }
    /* Fix #6: Report container styling without unsafe HTML injection */
    .report-container {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        margin: 10px 0;
        max-height: 600px;
        overflow-y: auto;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        line-height: 1.6;
        color: #212529;
    }
    .report-container h1, .report-container h2, .report-container h3 {
        color: #1f77b4;
    }
    .report-container p {
        margin-bottom: 10px;
    }
    .feedback-container {
        background-color: #fff3cd;
        padding: 15px;
        border-radius: 10px;
        border-left: 4px solid #ffc107;
        margin: 10px 0;
    }
    .debug-container {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 5px;
        border: 1px solid #ddd;
        font-family: 'Courier New', monospace;
        font-size: 12px;
    }
    .content-warning {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
def init_session_state():
    """Initialize session state variables"""
    if 'research_state' not in st.session_state:
        st.session_state.research_state = {}
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 0
    if 'is_running' not in st.session_state:
        st.session_state.is_running = False
    if 'start_time' not in st.session_state:
        st.session_state.start_time = None
    if 'end_time' not in st.session_state:
        st.session_state.end_time = None
    if 'research_history' not in st.session_state:
        st.session_state.research_history = []
    if 'total_retries' not in st.session_state:
        st.session_state.total_retries = 0
    if 'rate_limit_errors' not in st.session_state:
        st.session_state.rate_limit_errors = 0
    if 'show_debug' not in st.session_state:
        st.session_state.show_debug = False
    if 'last_topic' not in st.session_state:
        st.session_state.last_topic = ""
    if 'retry_details' not in st.session_state:
        st.session_state.retry_details = {}
    if 'pipeline_complete' not in st.session_state:
        st.session_state.pipeline_complete = False  # Fix #5: Track completion separately

init_session_state()

# Helper functions
def format_content(content: str, max_length: int = 1000) -> str:
    """Format and truncate content for display - truncate at sentence boundaries"""
    if not content:
        return "⚠️ No content available"
    if len(content) <= max_length:
        return content
    
    # Truncate at sentence boundary if possible
    truncated = content[:max_length]
    # Find last sentence-ending punctuation before the limit
    last_period = truncated.rfind('. ')
    last_exclamation = truncated.rfind('! ')
    last_question = truncated.rfind('? ')
    last_boundary = max(last_period, last_exclamation, last_question)
    
    if last_boundary > max_length // 2:  # Only use boundary if it's not too early
        return content[:last_boundary + 2] + "..."
    else:
        # Fall back to simple truncation at word boundary
        last_space = truncated.rfind(' ')
        if last_space > 0:
            return content[:last_space] + "..."
        return truncated + "..."

def get_status_badge(status: str) -> str:
    """Get HTML badge for status"""
    badge_classes = {
        'pending': 'status-badge status-pending',
        'running': 'status-badge status-running',
        'complete': 'status-badge status-complete',
        'error': 'status-badge status-error'
    }
    return f'<span class="{badge_classes.get(status, "status-badge status-pending")}">{status.upper()}</span>'

# Rate Limiter Class
class RateLimiter:
    """Rate limiter with incremental waits for UI responsiveness"""
    def __init__(self, calls_per_minute=8):
        self.calls_per_minute = calls_per_minute
        self.calls = []
        self.last_reset = time.time()
    
    def wait(self):
        """Wait if rate limit would be exceeded"""
        now = time.time()
        if now - self.last_reset >= 60:
            self.calls = []
            self.last_reset = now
        
        self.calls = [t for t in self.calls if now - t < 60]
        
        if len(self.calls) >= self.calls_per_minute:
            sleep_time = 60 - (now - self.calls[0]) + 1
            if sleep_time > 0:
                # Use 1-second increments for UI responsiveness
                for _ in range(int(sleep_time)):
                    time.sleep(1)
                    # Could check for cancellation here if needed
        
        self.calls.append(now)

# Create global rate limiter
rate_limiter = RateLimiter(calls_per_minute=8)

# Fix #1 & #2: Proper retry handling
def before_sleep(retry_state):
    """Callback to track retries before sleep - only fires on actual retries"""
    step_name = retry_state.fn.__name__
    attempt = retry_state.attempt_number
    
    # Update session state for UI
    st.session_state.total_retries += 1
    
    # Track per-step retries
    if step_name not in st.session_state.retry_details:
        st.session_state.retry_details[step_name] = 0
    st.session_state.retry_details[step_name] += 1
    
    # Show warning only on actual retries
    st.warning(f"🔄 Retrying {step_name}... (Attempt {attempt})")
    logger.warning(f"Retry attempt {attempt} for {step_name}")

def is_rate_limit_error(exception):
    """Check if exception indicates a rate limit error"""
    # Check for HTTP 429 status
    if isinstance(exception, HTTPStatusError):
        return exception.response.status_code == 429
    
    # Check for rate limit in error message (covers Mistral SDK)
    error_str = str(exception).lower()
    rate_limit_indicators = [
        'rate limit',
        'rate_limited', 
        '429',
        'too many requests',
        'quota exceeded',
        'resource exhausted',
        'throttled'
    ]
    return any(indicator in error_str for indicator in rate_limit_indicators)

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type(Exception),  # Catch all exceptions, we'll filter internally
    before_sleep=before_sleep
)
def invoke_with_retry(agent, messages, step_name="API Call"):
    """Invoke agent with retry logic for rate limits"""
    try:
        rate_limiter.wait()
        result = agent.invoke(messages)
        return result
        
    except Exception as e:
        if is_rate_limit_error(e):
            st.session_state.rate_limit_errors += 1
            logger.warning(f"Rate limit hit for {step_name}: {str(e)}")
            # Re-raise to trigger tenacity retry
            raise
        
        # Log but don't retry other errors
        logger.error(f"Non-retryable error in {step_name}: {str(e)}")
        raise

def run_pipeline_async(topic: str):
    """Run the research pipeline with rate limiting and retries"""
    try:
        st.session_state.start_time = datetime.now()
        st.session_state.current_step = 1
        st.session_state.is_running = True
        st.session_state.total_retries = 0
        st.session_state.rate_limit_errors = 0
        st.session_state.retry_details = {}
        st.session_state.last_topic = topic
        st.session_state.pipeline_complete = False  # Reset completion flag
        
        state = {}
        
        # Step 1: Search Agent
        st.session_state.research_state['step1_status'] = 'running'
        st.session_state.current_step = 1
        
        with st.spinner("🔍 Searching for information..."):
            search_agent = build_search_agent()
            search_result = invoke_with_retry(
                search_agent, 
                {"messages": [("user", f"Find recent, reliable and detailed information about: {topic}")]},
                "Search Agent"
            )
            state["search_results"] = search_result['messages'][-1].content
            st.session_state.research_state['search_results'] = state["search_results"]
            st.session_state.research_state['step1_status'] = 'complete'
            st.success("✅ Search completed!")
        
        time.sleep(1)
        
        # Step 2: Reader Agent
        st.session_state.research_state['step2_status'] = 'running'
        st.session_state.current_step = 2
        
        with st.spinner("📄 Scraping content from top sources..."):
            reader_agent = build_reader_agent()
            reader_result = invoke_with_retry(
                reader_agent,
                {"messages": [("user",
                    f"Based on the following search results about '{topic}', "
                    f"pick the most relevant URL and scrape it for deeper content.\n\n"
                    f"Search Results:\n{state['search_results'][:800]}"
                )]},
                "Reader Agent"
            )
            state['scraped_content'] = reader_result['messages'][-1].content
            st.session_state.research_state['scraped_content'] = state['scraped_content']
            st.session_state.research_state['step2_status'] = 'complete'
            st.success("✅ Scraping completed!")
        
        time.sleep(1)
        
        # Step 3: Writer Chain
        st.session_state.research_state['step3_status'] = 'running'
        st.session_state.current_step = 3
        
        with st.spinner("✍️ Writing the research report..."):
            research_combined = (
                f"SEARCH RESULTS : \n {state['search_results']} \n\n"
                f"DETAILED SCRAPED CONTENT : \n {state['scraped_content']}"
            )
            
            report_result = invoke_with_retry(
                writer_chain,
                {"topic": topic, "research": research_combined},
                "Writer Chain"
            )
            
            # Store the report
            if isinstance(report_result, dict):
                state["report"] = report_result.get('text', str(report_result))
            else:
                state["report"] = str(report_result)
            
            st.session_state.research_state['report'] = state["report"]
            st.session_state.research_state['step3_status'] = 'complete'
            st.success("✅ Report written!")
        
        time.sleep(1)
        
        # Step 4: Critic Review
        st.session_state.research_state['step4_status'] = 'running'
        st.session_state.current_step = 4
        
        with st.spinner("🔍 Reviewing report with Critic..."):
            feedback_result = invoke_with_retry(
                critic_chain,
                {"report": state['report']},
                "Critic Chain"
            )
            
            if isinstance(feedback_result, dict):
                state["feedback"] = feedback_result.get('text', str(feedback_result))
            else:
                state["feedback"] = str(feedback_result)
            
            st.session_state.research_state['feedback'] = state['feedback']
            st.session_state.research_state['step4_status'] = 'complete'
            st.success("✅ Review completed!")
        
        # Final state
        st.session_state.research_state = {**st.session_state.research_state, **state}
        st.session_state.end_time = datetime.now()
        st.session_state.is_running = False
        st.session_state.current_step = 5
        st.session_state.pipeline_complete = True  # Fix #5: Set completion flag
        
        # Save to history
        st.session_state.research_history.append({
            'topic': topic,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'state': st.session_state.research_state.copy(),
            'total_retries': st.session_state.total_retries,
            'rate_limit_errors': st.session_state.rate_limit_errors,
            'retry_details': st.session_state.retry_details.copy(),
            'report_length': len(state.get('report', ''))
        })
        
        # Fix #5: Don't call st.rerun() here - let the UI update naturally
        
    except Exception as e:
        st.session_state.is_running = False
        st.session_state.current_step = -1
        st.session_state.pipeline_complete = False
        st.error(f"Error in pipeline: {str(e)}")
        st.exception(e)
        raise

# Sidebar
with st.sidebar:
    st.title("🔬 Research Pipeline")
    st.markdown("---")
    
    # Research Input
    st.subheader("New Research")
    topic = st.text_input("Enter research topic:", placeholder="e.g., Quantum Computing Applications", value=st.session_state.last_topic)
    
    # Start button with disabled state
    col1, col2 = st.columns([2, 1])
    with col1:
        start_disabled = st.session_state.is_running or not topic
        start_button = st.button(
            "🚀 Start Research",
            disabled=start_disabled,
            use_container_width=True
        )
    with col2:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.research_state = {}
            st.session_state.current_step = 0
            st.session_state.is_running = False
            st.session_state.total_retries = 0
            st.session_state.rate_limit_errors = 0
            st.session_state.retry_details = {}
            st.session_state.last_topic = ""
            st.session_state.pipeline_complete = False
            st.rerun()
    
    # Status Section
    st.markdown("---")
    st.subheader("📊 Status")
    
    if st.session_state.start_time and st.session_state.end_time:
        duration = (st.session_state.end_time - st.session_state.start_time).total_seconds()
        st.metric("⏱️ Duration", f"{duration:.1f}s")
    
    # Only show retry metrics if there were actual retries
    if st.session_state.total_retries > 0:
        st.metric("🔄 Total Retries", st.session_state.total_retries)
        if st.session_state.retry_details:
            with st.expander("📋 Retry Details", expanded=False):
                for step, count in st.session_state.retry_details.items():
                    st.caption(f"{step}: {count} retries")
    
    if st.session_state.rate_limit_errors > 0:
        st.metric("⚠️ Rate Limit Errors", st.session_state.rate_limit_errors)
    
    # Pipeline Steps Status
    steps = [
        ("1. Search", st.session_state.research_state.get('step1_status', 'pending')),
        ("2. Scrape", st.session_state.research_state.get('step2_status', 'pending')),
        ("3. Write", st.session_state.research_state.get('step3_status', 'pending')),
        ("4. Critic", st.session_state.research_state.get('step4_status', 'pending'))
    ]
    
    for step_name, status in steps:
        st.markdown(f"{step_name} {get_status_badge(status)}", unsafe_allow_html=True)
    
    # Debug toggle
    st.markdown("---")
    if st.button("🐞 Toggle Debug Info"):
        st.session_state.show_debug = not st.session_state.show_debug
        st.rerun()
    
    # Research History
    if st.session_state.research_history:
        st.markdown("---")
        st.subheader("📜 History")
        for i, item in enumerate(reversed(st.session_state.research_history[-5:])):
            retry_info = ""
            if item.get('total_retries', 0) > 0:
                retry_info = f" (🔄{item['total_retries']})"
            if st.button(f"🔍 {item['topic'][:30]}...{retry_info} ({item['timestamp']})", key=f"history_{i}"):
                st.session_state.research_state = item['state']
                st.session_state.current_step = 5
                st.session_state.last_topic = item['topic']
                st.session_state.pipeline_complete = True
                st.rerun()

# Main content area
st.markdown('<h1 class="main-header">🔬 AI Research Pipeline</h1>', unsafe_allow_html=True)

# Show rate limit warning if too many errors
if st.session_state.rate_limit_errors > 2:
    st.warning("""
    ⚠️ **Rate Limit Notice**: You're experiencing rate limit errors. 
    The system is automatically retrying with delays. 
    Consider waiting a few minutes between research runs.
    """)

# Main layout with columns
col1, col2 = st.columns([2, 1])

with col1:
    # Progress indicator
    if st.session_state.is_running:
        st.info(f"🔄 Running Step {st.session_state.current_step}/4")
        progress = (st.session_state.current_step - 1) / 4
        st.progress(progress)
    
    # Display current step status
    if st.session_state.is_running:
        status_messages = {
            1: "🔍 Searching for information...",
            2: "📄 Scraping content from sources...",
            3: "✍️ Writing the research report...",
            4: "🔍 Reviewing with Critic..."
        }
        st.info(status_messages.get(st.session_state.current_step, "Processing..."))
    
    # Research Results
    if st.session_state.research_state:
        # Search Results
        if 'search_results' in st.session_state.research_state:
            with st.expander("🔍 Step 1: Search Results", expanded=False):
                search_content = st.session_state.research_state.get('search_results', '')
                if search_content:
                    st.markdown(format_content(search_content, 2000))
                else:
                    st.warning("⚠️ No search results available")
        
        # Scraped Content
        if 'scraped_content' in st.session_state.research_state:
            with st.expander("📄 Step 2: Scraped Content", expanded=False):
                scraped_content = st.session_state.research_state.get('scraped_content', '')
                if scraped_content:
                    st.markdown(format_content(scraped_content, 2000))
                else:
                    st.warning("⚠️ No scraped content available")
        
        # Final Report - Fix #6: Use safe rendering without unsafe_allow_html
        report_content = st.session_state.research_state.get('report', '')
        
        if report_content:
            st.markdown("---")
            st.markdown("## 📝 Final Research Report")
            
            # Display report length
            st.caption(f"📄 Report length: {len(report_content)} characters")
            
            # Fix #6: Use container for styling with safe markdown rendering
            with st.container():
                st.markdown(f'<div class="report-container">', unsafe_allow_html=True)
                # Render the report safely with markdown
                st.markdown(report_content)
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Download buttons
            col_dl1, col_dl2, col_dl3 = st.columns(3)
            with col_dl1:
                st.download_button(
                    label="📥 Download Report (TXT)",
                    data=report_content,
                    file_name=f"research_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    key="download_txt",
                    use_container_width=True
                )
            with col_dl2:
                json_data = {
                    "topic": topic if topic else "Unknown",
                    "timestamp": datetime.now().isoformat(),
                    "report": report_content,
                    "feedback": st.session_state.research_state.get('feedback', ''),
                    "total_retries": st.session_state.total_retries,
                    "rate_limit_errors": st.session_state.rate_limit_errors,
                    "retry_details": st.session_state.retry_details
                }
                st.download_button(
                    label="📊 Download Report (JSON)",
                    data=json.dumps(json_data, indent=2),
                    file_name=f"research_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    key="download_json",
                    use_container_width=True
                )
            with col_dl3:
                st.download_button(
                    label="📄 Download Report (Markdown)",
                    data=f"# Research Report: {topic}\n\n{report_content}\n\n## Feedback\n\n{st.session_state.research_state.get('feedback', 'No feedback available')}",
                    file_name=f"research_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    key="download_md",
                    use_container_width=True
                )
        else:
            st.warning("⚠️ No report content available. The pipeline may not have generated a report.")
        
        # Critic Feedback - Fix #6: Safe rendering
        feedback_content = st.session_state.research_state.get('feedback', '')
        if feedback_content:
            with st.expander("📊 Step 4: Critic Feedback", expanded=True):
                st.markdown("**Critic Review & Suggestions:**")
                with st.container():
                    st.markdown(f'<div class="feedback-container">', unsafe_allow_html=True)
                    st.markdown(feedback_content)
                    st.markdown('</div>', unsafe_allow_html=True)
        
        # Debug info
        if st.session_state.show_debug:
            with st.expander("🐞 Debug Information", expanded=True):
                st.markdown("### Session State Keys:")
                st.json(list(st.session_state.research_state.keys()))
                
                st.markdown("### Retry Information:")
                st.json({
                    "total_retries": st.session_state.total_retries,
                    "retry_details": st.session_state.retry_details,
                    "rate_limit_errors": st.session_state.rate_limit_errors
                })
                
                st.markdown("### Report Content Preview:")
                report_preview = report_content[:500] if report_content else "No report content"
                st.text(report_preview)

with col2:
    # Quick Stats
    report_content = st.session_state.research_state.get('report', '')
    if report_content:
        st.subheader("📈 Report Stats")
        
        # Word count
        words = len(report_content.split())
        chars = len(report_content)
        sentences = len(re.findall(r'[.!?]+', report_content))
        
        col_stats1, col_stats2 = st.columns(2)
        with col_stats1:
            st.metric("📝 Words", words)
        with col_stats2:
            st.metric("📏 Characters", chars)
        
        col_stats3, col_stats4 = st.columns(2)
        with col_stats3:
            st.metric("📊 Sentences", sentences)
        with col_stats4:
            reading_time = max(1, round(words / 200))
            st.metric("⏱️ Reading Time", f"{reading_time} min")
        
        # Extract potential sections
        sections = re.findall(r'^#{1,3}\s+(.+)$', report_content, re.MULTILINE)
        if sections:
            st.metric("📑 Sections", len(sections))
        
        # Feedback stats
        feedback_content = st.session_state.research_state.get('feedback', '')
        if feedback_content:
            feedback_words = len(feedback_content.split())
            st.metric("💬 Feedback Length", f"{feedback_words} words")
    
    # Pipeline metadata
    if st.session_state.research_state:
        st.markdown("---")
        st.caption("⚙️ Pipeline Details")
        st.caption(f"Topic: {topic if topic else 'N/A'}")
        if st.session_state.start_time and st.session_state.end_time:
            st.caption(f"Completed: {st.session_state.end_time.strftime('%H:%M:%S')}")
        if st.session_state.total_retries > 0:
            st.caption(f"🔄 Total Retries: {st.session_state.total_retries}")
        if st.session_state.rate_limit_errors > 0:
            st.caption(f"⚠️ Rate Limit Errors: {st.session_state.rate_limit_errors}")
        
        # Fix #7: Single completion UI - only here, not in multiple places
        st.markdown("---")
        st.subheader("📋 Status Summary")
        all_complete = all([
            st.session_state.research_state.get('step1_status') == 'complete',
            st.session_state.research_state.get('step2_status') == 'complete',
            st.session_state.research_state.get('step3_status') == 'complete',
            st.session_state.research_state.get('step4_status') == 'complete'
        ])
        
        # Fix #7: Only show completion UI when pipeline is complete and not running
        if all_complete and report_content and not st.session_state.is_running and st.session_state.pipeline_complete:
            st.success("✅ All steps completed successfully!")
            # Fix #7: Single balloons trigger
            st.balloons()

# Fix #5: Main execution block without st.rerun() in try block
if start_button and topic:
    with st.spinner("Running research pipeline..."):
        try:
            run_pipeline_async(topic)
            # Success message only - no st.rerun()
            st.success("✅ Research pipeline completed successfully!")
        except Exception as e:
            st.error(f"❌ Pipeline failed: {str(e)}")
            st.exception(e)
    # Force a rerun after the pipeline completes to update the UI
    st.rerun()

# Footer
st.markdown("---")
st.caption("Built with LangChain, MistralAI, and Streamlit | Research Pipeline v1.0")