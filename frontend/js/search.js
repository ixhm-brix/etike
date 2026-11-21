// The search page moved to the home page (form and map together). Old links
// to /search.html still work: they open the home page with the same search.
location.replace(`/${location.search}#trip`);
