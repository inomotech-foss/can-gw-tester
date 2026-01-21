"""GUI Configuration for centralized settings management.

Provides a single place to configure:
- Default interface names
- Timer intervals (stats refresh, etc.)
- UI behavior (auto-start, warnings, etc.)
- Log paths
"""

from dataclasses import dataclass, field
from pathlib import Path


def _get_project_logs_path() -> Path:
    """Get the project logs directory path, creating it if needed."""
    # Path relative to this file: wp4/src/wp4/gui/config.py -> wp4/logs
    logs_path = Path(__file__).parent.parent.parent.parent / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    return logs_path


@dataclass
class TimerConfig:
    """Timer interval configuration (in milliseconds).

    Attributes:
        stats_refresh_ms: Statistics refresh interval
        interface_status_ms: Interface status check interval
        min_refresh_ms: Minimum allowed refresh interval
        max_refresh_ms: Maximum allowed refresh interval
    """

    stats_refresh_ms: int = 500
    interface_status_ms: int = 100
    min_refresh_ms: int = 100
    max_refresh_ms: int = 10000


@dataclass
class TrafficControlConfig:
    """Traffic control default values.

    Attributes:
        default_delay_ms: Default delay in milliseconds
        max_delay_ms: Maximum allowed delay
        default_loss_pct: Default packet loss percentage
        max_loss_pct: Maximum allowed loss percentage
        default_jitter_ms: Default jitter in milliseconds
        max_jitter_ms: Maximum allowed jitter
    """

    default_delay_ms: int = 0
    max_delay_ms: int = 10000
    default_loss_pct: float = 0.0
    max_loss_pct: float = 100.0
    default_jitter_ms: float = 0.0
    max_jitter_ms: float = 1000.0


@dataclass
class InterfaceConfig:
    """CAN interface configuration.

    Attributes:
        iface0: First interface name
        iface1: Second interface name
        default_bitrate: Default bitrate for real CAN interfaces
        min_bitrate: Minimum bitrate
        max_bitrate: Maximum bitrate
    """

    iface0: str = "can0"
    iface1: str = "can1"
    default_bitrate: int = 500000
    min_bitrate: int = 10000
    max_bitrate: int = 1000000


@dataclass
class LoggingConfig:
    """Logging configuration.

    Attributes:
        default_path: Default log directory path
        auto_enable: Whether to enable logging by default
        filename_format: Format string for auto-generated filenames
    """

    default_path: Path = field(default_factory=lambda: _get_project_logs_path())
    auto_enable: bool = False
    filename_format: str = "gateway_{timestamp}.blf"


@dataclass
class WarningConfig:
    """Warning thresholds for extreme values.

    Attributes:
        high_loss_threshold: Packet loss percentage to warn about
        high_delay_threshold: Delay in ms to warn about
        jitter_exceeds_delay: Whether to warn when jitter > delay
    """

    high_loss_threshold: float = 50.0
    high_delay_threshold: int = 5000
    jitter_exceeds_delay: bool = True


@dataclass
class GuiConfig:
    """Main GUI configuration container.

    Example:
        ```python
        # Use defaults
        config = GuiConfig()

        # Customize
        config = GuiConfig(
            interfaces=InterfaceConfig(iface0="vcan0", iface1="vcan1"),
            timers=TimerConfig(stats_refresh_ms=1000),
        )
        ```

    Attributes:
        interfaces: CAN interface configuration
        timers: Timer interval configuration
        traffic_control: Traffic control default values
        logging: Logging configuration
        warnings: Warning thresholds
    """

    interfaces: InterfaceConfig = field(default_factory=InterfaceConfig)
    timers: TimerConfig = field(default_factory=TimerConfig)
    traffic_control: TrafficControlConfig = field(default_factory=TrafficControlConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    warnings: WarningConfig = field(default_factory=WarningConfig)

    @classmethod
    def for_vcan(cls) -> "GuiConfig":
        """Create configuration for virtual CAN interfaces.

        Returns:
            GuiConfig with vcan0/vcan1 interfaces
        """
        return cls(
            interfaces=InterfaceConfig(iface0="vcan0", iface1="vcan1"),
        )

    @classmethod
    def for_hardware(cls, iface0: str = "can0", iface1: str = "can1") -> "GuiConfig":
        """Create configuration for hardware CAN interfaces.

        Args:
            iface0: First interface name
            iface1: Second interface name

        Returns:
            GuiConfig with specified hardware interfaces
        """
        return cls(
            interfaces=InterfaceConfig(iface0=iface0, iface1=iface1),
        )


# Default configuration instance
_default_config: GuiConfig = GuiConfig()


def get_default_config() -> GuiConfig:
    """Get the default GUI configuration.

    Returns:
        GuiConfig: Default configuration instance
    """
    return _default_config


def set_default_config(config: GuiConfig) -> None:
    """Set the default GUI configuration.

    Args:
        config: New default configuration
    """
    global _default_config
    _default_config = config
