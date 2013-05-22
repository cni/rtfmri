
<script>
var update_interval = 1000;
var graph;
graph = new Rickshaw.Graph.Ajax( {
  	element: document.querySelector("#chart"),
  	width: 800, height: 200, renderer: "line", interpolation: "linear",
  	dataURL: "data.json",
    series: [{name:"Mean Displacement", color:"#c05020"}],
    onComplete: function(transport) {
        var graph = transport.graph;

        var detail = new Rickshaw.Graph.HoverDetail({
            graph: graph,
            xFormatter: function(x) { return x + " seconds" },
            yFormatter: function(y) { return y + " mm" },
        });

        var x_axis = new Rickshaw.Graph.Axis.X({
            graph: graph,
        });
        x_axis.graph.update();

        var y_axis = new Rickshaw.Graph.Axis.Y({
            graph: graph,
            tickFormat: Rickshaw.Fixtures.Number.formatKMBT,
        });
        y_axis.graph.update();

        var legend = new Rickshaw.Graph.Legend({
            graph: graph,
            element: document.querySelector('#legend')
        });
        legend.graph.update();

        //var slider = new Rickshaw.Graph.RangeSlider({
        //    graph: graph,
        //    element: document.querySelector("#slider"),
        //});
        //slider.graph.update();
    }
});

// add some data every so often
// data come in a structure like this: [{"data": [{"y": 0.0, "x": 0.0}, {"y": 0.0, "x": 2.0}, {"y": 0.456, "x": 4.0}], "name": "Mean Displacement"}]
// TODO: time-out after the data stop coming, so that we don't poll forever.
var num_tries = 0;
var iv = setInterval( function() {
    var last_time_ind = graph.args.series[0]['data'].length
    graph.dataURL = 'data.json?start=' + last_time_ind
    graph.request()
    // Stop polling if we haven't received any data in a while.
    if(num_tries>100) clearInterval(iv);
}, update_interval );
</script>

