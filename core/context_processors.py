def client_type_filter(request):
    """
    Context processor to make client_type_filter available in all templates.
    Gets the filter from session, with fallback to GET parameter or 'all'.
    """
    if request.user.is_authenticated:
        # Check if filter is being set via GET parameter
        if 'client_type' in request.GET:
            client_type = request.GET.get('client_type', 'all')
            # Store in session
            request.session['client_type_filter'] = client_type
        else:
            # Get from session, default to 'all'
            client_type = request.session.get('client_type_filter', 'all')
    else:
        client_type = 'all'
    
    return {
        'client_type_filter': client_type,
    }

