import uuid
import time
import random
import logging
import math
from datetime import datetime
from typing import Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S,%f",
)
logger = logging.getLogger(__name__)

class DroneClient:
    def __init__(self, max_iterations: int = 100, use_constant_runner: bool = True):
        self.connection_id = str(uuid.uuid4())
        self.x_position = 0.0
        self.y_position = 0.0
        self.battery = 100.0
        self.iterations = 0
        self.total_distance = 0.0
        self.start_time = time.time()
        self.red_cooldown = 0
        self.previous_status = "GREEN"
        self.previous_dust = 0.0
        self.previous_wind = 0.0
        self.max_iterations = max_iterations
        self.max_altitude = 8.0
        self.safe_altitude = 2.0  # Harsh condition
        self.use_constant_runner = use_constant_runner
        self.telemetry_history = []  # For constantRunner

    def constant_runner(self, telemetry: List[Dict]) -> Dict[str, float]:
        """Keeps drone at RED-safe altitude with constant speed."""
        initial = {"altitude": 5.0, "speed": 4.0, "movement": "fwd"}
        nextodd = {"altitude": -1.0, "speed": 4.0, "movement": "fwd"}  # To 2.0
        nexteven = {"altitude": 1.0, "speed": 4.0, "movement": "fwd"}  # To 3.0 or 4.0

        if len(telemetry) == 0:
            return initial
        return nextodd if len(telemetry) % 2 != 0 else nexteven

    def generate_telemetry(self, command: Dict[str, float]) -> Dict[str, any]:
        """Simulate telemetry based on command and environmental conditions."""
        try:
            self.iterations += 1
            speed = command.get("speed", 0.0)
            altitude = command.get("altitude", 0.0)
            movement = command.get("movement", "fwd")

            # Validate inputs
            if not isinstance(speed, (int, float)) or speed < 0:
                logger.error(f"Invalid speed: {speed}")
                speed = 0.0
            if not isinstance(altitude, (int, float)):
                logger.error(f"Invalid altitude: {altitude}")
                altitude = 0.0

            # Update position (relative altitude)
            if movement == "fwd" and speed > 0:
                self.x_position += speed
                self.total_distance += speed
            self.y_position = min(max(self.y_position + altitude, 0.0), self.max_altitude)
            logger.debug(f"Updated position: x={self.x_position}, y={self.y_position}")

            # Simulate battery drain (1.5x for harsh conditions)
            battery_drain = 1.5 * (
                1.0 * speed / 5.0 + 0.5 * self.y_position / 8.0 + random.uniform(0.1, 0.5)
            )
            self.battery = max(0.0, self.battery - battery_drain)

            # Simulate environmental conditions
            wind_speed = min(
                100.0,
                max(
                    40.0,  # Slightly less harsh
                    self.previous_wind
                    + random.uniform(-20.0, 20.0) * (1.0 + speed / 5.0),
                ),
            )
            dust_level = min(
                100.0,
                max(
                    40.0,
                    self.previous_dust
                    + random.uniform(-30.0, 30.0) * (1.0 + wind_speed / 50.0),
                ),
            )

            # Determine sensor status
            sensor_status = "GREEN"
            if dust_level > 80 or wind_speed > 80:
                sensor_status = "RED"
            elif dust_level > 60 or wind_speed > 60:
                sensor_status = "YELLOW"

            # Simulate gyroscope
            gyroscope = [
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
            ]

            telemetry = {
                "x_position": self.x_position,
                "y_position": self.y_position,
                "battery": self.battery,
                "gyroscope": gyroscope,
                "wind_speed": wind_speed,
                "dust_level": dust_level,
                "sensor_status": sensor_status,
            }
            self.telemetry_history.append(telemetry)
            logger.debug(f"Generated telemetry: {telemetry}")
            return telemetry
        except Exception as e:
            logger.error(f"Error generating telemetry: {str(e)}")
            return {
                "x_position": self.x_position,
                "y_position": self.y_position,
                "battery": self.battery,
                "gyroscope": [0.0, 0.0, 0.0],
                "wind_speed": 0.0,
                "dust_level": 0.0,
                "sensor_status": "RED",
            }

    def predict_crash(self, command: Dict[str, float], telemetry: Dict[str, any]) -> bool:
        """Predict if the command will cause a crash."""
        try:
            speed = command.get("speed", 0.0)
            altitude = command.get("altitude", 0.0)
            sensor_status = telemetry.get("sensor_status", "GREEN")
            battery = telemetry.get("battery", 0.0)

            # Predict resulting y_position
            predicted_y_position = min(max(self.y_position + altitude, 0.0), self.max_altitude)

            if (
                predicted_y_position > self.safe_altitude
                and (
                    sensor_status == "RED"
                    or self.previous_status == "RED"
                    or self.red_cooldown > 0
                )
            ):
                logger.warning("Crash predicted: Unsafe altitude with RED status")
                return True
            if predicted_y_position > self.max_altitude:
                logger.warning(f"Crash predicted: Altitude {predicted_y_position} exceeds max {self.max_altitude}")
                return True
            if battery < 15 and speed > 0:  # Harsh condition
                logger.warning("Crash predicted: Low battery with movement")
                return True
            return False
        except Exception as e:
            logger.error(f"Error predicting crash: {str(e)}")
            return True

    def send_command(self, telemetry: Dict[str, any]) -> Dict[str, any]:
        """Generate and send a command based on telemetry."""
        try:
            # Default command (randomized for harsh conditions)
            command = {
                "speed": random.uniform(3.0, 7.0),
                "altitude": random.uniform(-2.0, 2.0),
                "movement": "fwd"
            }

            # Track environmental trends
            dust_trend = telemetry["dust_level"] - self.previous_dust
            wind_trend = telemetry["wind_speed"] - self.previous_wind
            logger.info(f"Environmental trends: dust_trend={dust_trend:.2f}, wind_trend={wind_trend:.2f}")

            # Handle sensor status
            if telemetry["sensor_status"] == "RED":
                command = {"speed": 0.0, "altitude": -self.y_position, "movement": "fwd"}
                self.red_cooldown = 5  # Reduced for balance
                logger.info("Sensor status RED: Forcing landing")
            elif telemetry["sensor_status"] == "YELLOW":
                command["speed"] = 3.0
                command["altitude"] = min(command["altitude"], self.safe_altitude - self.y_position)
                self.red_cooldown = max(0, self.red_cooldown - 1)
                logger.info("Sensor status YELLOW: Reducing altitude and speed")
            elif self.red_cooldown > 0:
                command["speed"] = 3.0
                command["altitude"] = min(command["altitude"], self.safe_altitude - self.y_position)
                logger.info(f"RED cooldown active ({self.red_cooldown} iterations remaining)")
                self.red_cooldown -= 1
            else:
                command["altitude"] = random.uniform(-2.0, 2.0)

            # Adaptive environmental response
            if dust_trend > 10 or wind_trend > 10:
                command["speed"] = min(command["speed"], 3.0)
                command["altitude"] = min(command["altitude"], self.safe_altitude - self.y_position)
                logger.info("High environmental trend detected: Reducing speed and altitude")

            # Battery management
            if telemetry["battery"] < 50:
                command["speed"] = min(command["speed"], 3.0)
                command["altitude"] = min(command["altitude"], 2.0 - self.y_position)
                logger.info("Low battery (<50%): Entering power-saving mode")
            if telemetry["battery"] < 20:
                command = {"speed": 0.0, "altitude": -self.y_position, "movement": "fwd"}
                logger.info("Critical battery (<20%): Forcing landing")

            # Predict crash
            if self.predict_crash(command, telemetry):
                logger.warning("Crash predicted: Forcing safe command")
                command = {"speed": 0.0, "altitude": -self.y_position, "movement": "fwd"}

            # Update previous values
            self.previous_status = telemetry["sensor_status"]
            self.previous_dust = telemetry["dust_level"]
            self.previous_wind = telemetry["wind_speed"]

            logger.info(f"Sending command: {command}")
            return command
        except Exception as e:
            logger.error(f"Error sending command: {str(e)}")
            return {"speed": 0.0, "altitude": -self.y_position, "movement": "fwd"}

    def run(self):
        """Main control loop."""
        logger.info(f"Connected with ID: {self.connection_id}")
        command = {"speed": 5.0, "altitude": 0.0, "movement": "fwd"}
        logger.info(f"Sending initial command: {command}")

        while self.battery > 0 and self.iterations < self.max_iterations:
            time.sleep(0.05)
            try:
                telemetry = self.generate_telemetry(command)
                metrics = {"iterations": self.iterations, "total_distance": self.total_distance}
                logger.info(f"Telemetry: {telemetry}, Metrics: {metrics}")

                # Check for crash
                if (
                    telemetry["y_position"] > self.safe_altitude
                    and (
                        telemetry["sensor_status"] == "RED"
                        or self.previous_status == "RED"
                    )
                ):
                    crash_message = (
                        f"Drone has crashed due to unsafe altitude with RED sensor status. "
                        f"Maximum safe altitude is {self.safe_altitude}. Final telemetry: "
                        f"X-{telemetry['x_position']}-Y-{telemetry['y_position']}-"
                        f"BAT-{telemetry['battery']}-GYR-{telemetry['gyroscope']}-"
                        f"WIND-{telemetry['wind_speed']}-DUST-{telemetry['dust_level']}-"
                        f"SENS-{telemetry['sensor_status']}"
                    )
                    logger.error(
                        f"Drone crashed: {{'status': 'crashed', 'message': '{crash_message}', "
                        f"'metrics': {metrics}, 'connection_terminated': True}}"
                    )
                    break

                # Use constantRunner if enabled
                if self.use_constant_runner:
                    command = self.constant_runner(self.telemetry_history)
                    if self.predict_crash(command, telemetry):
                        logger.warning("Crash predicted: Forcing safe command")
                        command = {"speed": 0.0, "altitude": -self.y_position, "movement": "fwd"}
                    logger.info(f"constantRunner command: {command}")
                else:
                    command = self.send_command(telemetry)

            except Exception as e:
                logger.error(f"Error in control loop: {str(e)}")
                break

        # Final metrics
        flight_duration = time.time() - self.start_time
        logger.info(f"Final metrics: {metrics}")
        logger.info(f"Commands sent: {self.iterations}")
        logger.info(f"Flight duration: {flight_duration:.2f}s")
        logger.info(f"Maximum distance traveled: {self.total_distance:.2f} units")

if __name__ == "__main__":
    drone = DroneClient(max_iterations=100, use_constant_runner=True)
    drone.run()