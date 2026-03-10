// A simple hollow cylinder demo
wall_thickness = 2;  // mm
height = 20;         // mm
radius = 10;         // mm

module cylinder_shell(r, h, wall) {
    difference() {
        cylinder(r=r, h=h);
        translate([0, 0, -1])
            cylinder(r=r - wall, h=h + 2);
    }
}

cylinder_shell(radius, height, wall_thickness);
