--[[
Batch Mesh Processing Script for GraphiteThree

This Lua script automates the batch processing of mesh files using GraphiteThree's scene_graph API.

Features:
- Scans the input directory for files matching the pattern 'Sweep <ID> extract.ply'.
- For each mesh file found:
    * Loads the mesh
    * Smooths the point set
    * Repairs the surface
    * Remeshes the mesh
    * Saves both a high and low resolution OBJ file to the output directory
    * Clears the scene to release memory before processing the next mesh
- Prints progress and error messages to the console for debugging and monitoring.

Usage:
- Set 'input_dir' and 'output_dir' to your desired paths.
- Place this script in the GraphiteThree scripting environment and run it.

--]]

input_dir = "E:/VRock2B/VRock2B_10Apr_FinalAddition"
output_dir = "E:/VRock2B/10AprExports"
ids = {}

local p = io.popen('dir "'..input_dir..'" /b')
for file in p:lines() do
    local id = string.match(file, "^Sweep (%d+) extract%.ply$")
    if id then
        table.insert(ids, tonumber(id))
    end
end
p:close()

for i, id in ipairs(ids) do
    local id_str = tostring(id)
    local file_path = string.format("%s/Sweep %s extract.ply", input_dir, id_str)
    print("Processing file: " .. file_path)
    scene_graph.load_object(file_path)

    local object = scene_graph.current()
    if not object then
        print("Failed to load object for ID: " .. id_str)
        break
    end

    print("Smoothing...")
    object.query_interface("OGF::MeshGrobPointsCommands").smooth_point_set({nb_iterations="1", nb_neighbors="45"})
    print("Repairing surface...")
    object.query_interface("OGF::MeshGrobSurfaceCommands").repair_surface(1e-06, 0.03, 0.001, 2000, 0, false)
    print("Remeshing...")
    object.query_interface("OGF::MeshGrobSurfaceCommands").remesh_smooth("remesh", 50000, 0, 0.5, true, 3, 5, 30, 7, 10000)

    local high_path = string.format("%s/%s_high.obj", output_dir, id_str)
    print("Saving high: " .. high_path)
    object.save(high_path)

    local remesh = scene_graph.find_or_create_object("OGF::MeshGrob","remesh")
    if remesh then
        local low_path = string.format("%s/%s_low.obj", output_dir, id_str)
        print("Saving low: " .. low_path)
        remesh.save(low_path)
    else
        print("Remesh object not found for ID: " .. id_str)
    end

    -- Optionally, add a delay if supported:
    -- os.execute("sleep 1")

    -- Clear the scene to release memory and remove loaded mesh
    scene_graph.clear()
end

print("Batch processing complete")
main.stop()