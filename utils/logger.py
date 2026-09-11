import logging
import sys
from rich.logging import RichHandler
from rich.console import Console

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configura e restituisce un logger con output formattato Rich."""
    
    # Crea logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Evita handler duplicati
    if logger.handlers:
        return logger
    
    # Handler Rich per output formattato
    console = Console(stderr=True)
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=False
    )
    
    # Formato per Rich
    rich_handler.setFormatter(logging.Formatter('%(message)s'))
    
    # Aggiungi handler
    logger.addHandler(rich_handler)
    
    return logger

def print_success(message: str):
    """Stampa un messaggio di successo."""
    console = Console()
    console.print(f"[green]✓[/green] {message}")

def print_error(message: str):
    """Stampa un messaggio di errore."""
    console = Console()
    console.print(f"[red]✗[/red] {message}")

def print_warning(message: str):
    """Stampa un messaggio di warning."""
    console = Console()
    console.print(f"[yellow]⚠[/yellow] {message}")

def print_info(message: str):
    """Stampa un messaggio informativo."""
    console = Console()
    console.print(f"[blue]ℹ[/blue] {message}")