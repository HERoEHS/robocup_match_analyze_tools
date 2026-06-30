# Ball position and covariance in the global coordinate frame
# Publishes each robot's globally transformed ball observation and uncertainty

# Ball detection flag (true: ball observed, false: ball lost)
bool detected

# Global ball position x (meters)
float64 x

# Global ball position y (meters)
float64 y

# 2x2 covariance matrix (row-major): [xx, xy, yx, yy]
float64[4] covariance

# ID of the observing robot
int32 robot_id

# Observation timestamp
builtin_interfaces/Time timestamp
