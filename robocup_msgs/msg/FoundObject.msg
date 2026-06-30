string name
uint32 id
geometry_msgs/Vector3 pos
sensor_msgs/RegionOfInterest roi
float32 var_x
float32 var_y
float32 var_z
# Object velocity in the same frame as pos (m/s). Defaults to 0 when unset
# (non-breaking field; consumers that ignore it are unaffected).
geometry_msgs/Vector3 velocity
# Detection confidence [0,1] from the detector backend. Defaults to 0 when unset
# (non-breaking field; consumers that ignore it are unaffected).
float32 score
