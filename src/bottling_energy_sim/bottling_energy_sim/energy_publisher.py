import rclpy
from rclpy.node import Node
import yaml
from std_msgs.msg import String
import importlib.resources as pkg_resources
from datetime import datetime, timezone

class EnergyPublisher(Node):
    def __init__(self):
        super().__init__("energy_publisher")
        # Increase queue depth for higher rate
        self.publisher_ = self.create_publisher(String, "bottling_energy", 20)

        # Load YAML bundled in package
        with pkg_resources.files(__package__).joinpath("data/bottling_sim.yaml").open("r") as f:
            self.data = yaml.safe_load(f)["bottling_line_energy_data"]

        self.index = 0
        # 10 Hz publishing (0.1s period)
        self.timer = self.create_timer(0.5, self.publish_next)

    def publish_next(self):
        row = dict(self.data[self.index])
        # Use real-time timestamp so charts move forward
        row["timestamp"] = datetime.now(timezone.utc).isoformat()
        msg = String()
        msg.data = yaml.safe_dump(row)
        self.publisher_.publish(msg)
        self.get_logger().info(f"Published data at index {self.index}")
        self.index = (self.index + 1) % len(self.data)

def main(args=None):
    rclpy.init(args=args)
    node = EnergyPublisher()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
