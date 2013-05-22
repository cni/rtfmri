
<script>
var update_interval = 1000;
var graph;
graph = new Rickshaw.Graph.Ajax( {
  	element: document.querySelector("#graph"),
  	width: 800, height: 200, renderer: "line", interpolation: "linear", min: "auto",
  	dataURL: "data.json",
    series: [{name:"Mean Displacement", color:"#707070"},
             {name:"Translation_X", color:"#a04020"},
             {name:"Translation_Y", color:"#c06030"},
             {name:"Translation_Z", color:"#e08040"},
             {name:"Rotation_X", color:"#2080c0"},
             {name:"Rotation_Y", color:"#20a0d0"},
             {name:"Rotation_Z", color:"#20c0e0"}],
    onComplete: function(transport) {
        var graph = transport.graph;

        var detail = new Rickshaw.Graph.HoverDetail({
            graph: graph,
            xFormatter: function(x) { return x + " seconds" },
            yFormatter: function(y) { return y + " mm/deg" },
        });

        var x_axis = new Rickshaw.Graph.Axis.X({
            graph: graph,
        });

        var y_axis = new Rickshaw.Graph.Axis.Y({
            graph: graph,
            tickFormat: Rickshaw.Fixtures.Number.formatKMBT,
        });

        var legend = new Rickshaw.Graph.Legend({
            graph: graph,
            element: document.querySelector('#legend')
        });

        var shelving = new Rickshaw.Graph.Behavior.Series.Toggle({
            graph: graph,
            legend: legend
        });

        var highlighter = new Rickshaw.Graph.Behavior.Series.Highlight({
            graph: graph,
            legend: legend
        });

        var slider = new Rickshaw.Graph.RangeSlider({
            graph: graph,
            element: document.querySelector("#slider"),
        });
        graph.update();
    },
    onError: function () {
        if (graph.num_ajax_errors > 3) clearInterval(iv);
    }
});

// add some data every so often
// data come in a structure like this: [{"data": [{"y": 0.0, "x": 0.0}, {"y": 0.0, "x": 2.0}, {"y": 0.456, "x": 4.0}], "name": "Mean Displacement"}]
// TODO: time-out after the data stop coming, so that we don't poll forever.
var num_tries = 0;
var iv = setInterval( function() {
    var last_time_ind = graph.args.series[0]['data'].length
    graph.dataURL = 'data.json?start=' + last_time_ind
    var num_appended = graph.request()
    // Stop polling if we haven't received any data in a while.
    if (num_appended==0) num_tries++;
    //if (num_tries>10) clearInterval(iv);
}, update_interval );

</script>

