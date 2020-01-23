from gramps.version import major_version

register(GRAMPLET,
         id = "selectaddonsource",
         name = _("Select addon source"),
         description = _("Select addon source"),
         status = STABLE,
         version = '0.0.12',
         gramps_target_version =  major_version,
         fname = "selectaddonsource.py",
         gramplet = 'SelectAddonSource',
         height = 375,
         detached_width = 510,
         detached_height = 480,
         expand = True,
         gramplet_title = _("Third party addons management"),
         help_url="",
         include_in_listing = True,
         navtypes=["Dashboard"],
        )
