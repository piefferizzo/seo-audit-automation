import logging
from rich.logging import RichHandler
from rich.console import Console


# ---------------------------------------------------------------------------
# COSTANTI — Configurazione logging
# ---------------------------------------------------------------------------
DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(message)s"


def setup_logger(name: str, level: int = DEFAULT_LOG_LEVEL) -> logging.Logger:
    """Configura e restituisce un logger con output formattato Rich.
    
    Args:
        name: Nome del logger (tipicamente il nome della classe)
        level: Livello di logging (default: INFO)
    
    Returns:
        Logger configurato
    """
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
    rich_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    
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