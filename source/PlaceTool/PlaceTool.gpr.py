from gramps.version import major_version

register(GRAMPLET,
         id = "PlaceTool",
         name = _("PlaceTool"),
         description = _("Gramplet to manipulate multiple places"),
         status = STABLE,
         version = '1.0.9',
         gramps_target_version = major_version,
         fname = "PlaceTool.py",
         gramplet = 'PlaceTool',
         height = 375,
         detached_width = 510,
         detached_height = 480,
         expand = True,
         gramplet_title = _("PlaceTool"),
         help_url="PlaceTool Gramplet",
         include_in_listing = True,
         navtypes=["Place"],
        )
